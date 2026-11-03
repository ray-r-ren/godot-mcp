"""Static reading of a Godot 4 project's text files (scenes, scripts, project.godot) in Python.

Works on projects that don't compile, so inspect_project can describe broken projects too."""

from __future__ import annotations

import re
from pathlib import Path

from .common import read_project_godot, rel_to_res, resolve_uid, unquote

SPECIAL_KEYS = {
    4194305: "Escape", 4194306: "Tab", 4194307: "Backtab", 4194308: "Backspace", 4194309: "Enter",
    4194310: "Kp Enter", 4194311: "Insert", 4194312: "Delete", 4194313: "Pause", 4194314: "Print",
    4194317: "Home", 4194318: "End", 4194319: "Left", 4194320: "Up", 4194321: "Right", 4194322: "Down",
    4194323: "PageUp", 4194324: "PageDown", 4194325: "Shift", 4194326: "Ctrl", 4194327: "Meta",
    4194328: "Alt", 4194329: "CapsLock", 32: "Space",
}
for _i in range(1, 13):
    SPECIAL_KEYS[4194331 + _i] = f"F{_i}"
MOUSE = {1: "mouse_left", 2: "mouse_right", 3: "mouse_middle", 4: "mouse_wheel_up", 5: "mouse_wheel_down"}


def key_name(code: int) -> str:
    if code in SPECIAL_KEYS:
        return SPECIAL_KEYS[code]
    if 33 <= code <= 126:
        return chr(code).upper()
    return f"key#{code}"


_OBJ = re.compile(r"Object\((InputEvent\w+),(.*?)\)\s*(?=,\s*Object\(|\]|$)", re.S)


def parse_events(raw: str) -> list[str]:
    out = []
    for m in _OBJ.finditer(raw):
        cls, body = m.group(1), m.group(2)
        props = dict(re.findall(r'"(\w+)":([^,]+)', body))
        if cls == "InputEventKey":
            code = int(props.get("physical_keycode", "0") or 0) or int(props.get("keycode", "0") or 0)
            out.append(key_name(code))
        elif cls == "InputEventMouseButton":
            out.append(MOUSE.get(int(props.get("button_index", "0")), "mouse_button"))
        elif cls == "InputEventJoypadButton":
            out.append(f"joypad_button_{props.get('button_index', '?')}")
        elif cls == "InputEventJoypadMotion":
            out.append(f"joypad_axis_{props.get('axis', '?')}{'+' if float(props.get('axis_value', '1')) > 0 else '-'}")
        else:
            out.append(cls)
    return out


def input_actions(project: Path) -> dict[str, list[str]]:
    cfg = read_project_godot(project)
    return {k: parse_events(v) for k, v in cfg.get("input", {}).items()}


def autoloads(project: Path) -> dict[str, str]:
    cfg = read_project_godot(project)
    return {k: (unquote(v) or "").lstrip("*") for k, v in cfg.get("autoload", {}).items()}


_HDR = re.compile(r"^\[(\w+)(.*)\]\s*$")
_ATTR = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\[[^\]]*\]|\S+)')


def _attrs(s: str) -> dict[str, str]:
    return {k: v.strip('"') for k, v in _ATTR.findall(s)}


def parse_tscn(path: Path, project: Path) -> dict:
    """Read a .tscn: ext resources, nodes (name, type, parent, script, instance), connections."""
    text = path.read_text(errors="replace")
    ext: dict[str, dict] = {}
    nodes: list[dict] = []
    conns: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = _HDR.match(line)
        if m:
            kind, rest = m.group(1), m.group(2)
            a = _attrs(rest)
            cur = None
            if kind == "ext_resource":
                p = a.get("path") or ""
                if not p and a.get("uid"):
                    p = resolve_uid(project, a["uid"]) or a["uid"]
                ext[a.get("id", "")] = {"type": a.get("type", ""), "path": p, "uid": a.get("uid")}
            elif kind == "node":
                inst = re.search(r'instance=ExtResource\(\s*"([^"]+)"\s*\)', rest)
                cur = {"name": a.get("name", "?"), "type": a.get("type"), "parent": a.get("parent"),
                       "instance": ext.get(inst.group(1), {}).get("path") if inst else None}
                g = re.search(r"groups=\[([^\]]*)\]", rest)
                if g:
                    cur["groups"] = re.findall(r'"([^"]+)"', g.group(1))
                nodes.append(cur)
            elif kind == "connection":
                conns.append({"signal": a.get("signal"), "from": a.get("from"), "to": a.get("to"), "method": a.get("method")})
            continue
        if cur is not None:
            sm = re.match(r'^script\s*=\s*ExtResource\(\s*"([^"]+)"\s*\)', line)
            if sm:
                cur["script"] = ext.get(sm.group(1), {}).get("path")
    for n in nodes:
        par = n.get("parent")
        n["path"] = "." if par is None else (n["name"] if par == "." else f"{par}/{n['name']}")
        if not n.get("type"):
            n["type"] = f"instance of {n['instance']}" if n.get("instance") else "?"
    return {"ext": ext, "nodes": nodes, "connections": conns}


def parse_script(path: Path) -> dict:
    text = path.read_text(errors="replace")
    info: dict = {"extends": None, "class_name": None, "methods": [], "signals": [], "exports": [], "lines": text.count("\n") + 1}
    for line in text.splitlines():
        s = line.strip()
        if m := re.match(r"^extends\s+(\S+)", s):
            info["extends"] = m.group(1)
        elif m := re.match(r"^class_name\s+(\w+)", s):
            info["class_name"] = m.group(1)
            if e := re.search(r"\bextends\s+(\S+)", s):
                info["extends"] = e.group(1)
        if line.startswith(("func ", "static func ")):
            if m := re.match(r"^(?:static\s+)?func\s+(\w+)\s*\(([^)]*)\)", line):
                info["methods"].append(f"{m.group(1)}({m.group(2).strip()})")
        elif line.startswith("signal "):
            if m := re.match(r"^signal\s+(\w+(?:\([^)]*\))?)", line):
                info["signals"].append(m.group(1))
        elif m := re.match(r"^@export\w*(?:\([^)]*\))?\s+(?:@\w+\s+)*var\s+(\w+)(.*)$", line):
            info["exports"].append((m.group(1) + m.group(2).split("#")[0]).strip()[:80])
    return info


def missing_references(project: Path, scene_paths: list[Path]) -> list[dict]:
    """ext_resource paths in scenes that point at files that don't exist."""
    out = []
    for sp in scene_paths:
        try:
            parsed = parse_tscn(sp, project)
        except OSError:
            continue
        text_lines = sp.read_text(errors="replace").splitlines()
        for r in parsed["ext"].values():
            p = r.get("path") or ""
            if p.startswith("res://"):
                if not (project / p[6:]).exists():
                    line = next((i + 1 for i, ln in enumerate(text_lines) if p in ln and ln.startswith("[ext_resource")), None)
                    out.append({"file": rel_to_res(str(sp.relative_to(project))), "line": line,
                                "message": f"references {p}, which does not exist"})
            elif p.startswith("uid://"):
                out.append({"file": rel_to_res(str(sp.relative_to(project))), "line": None,
                            "message": f"references {p}, which matches no file in the project"})
    return out


def list_files(project: Path, suffixes: tuple[str, ...]) -> list[Path]:
    out = []
    for p in sorted(project.rglob("*")):
        rel = p.relative_to(project)
        if rel.parts and (rel.parts[0] in (".godot", "addons_disabled") or rel.parts[0].startswith(".")):
            continue
        if any(part == "_skillnet" for part in rel.parts):
            continue
        if p.is_file() and p.suffix in suffixes:
            out.append(p)
    return out
