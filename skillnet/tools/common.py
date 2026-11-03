"""Shared helpers: the Godot engine process, log parsing, project state and zips."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from skillnet_sdk import ToolContext, ToolError

GODOT = os.environ.get("SKILLNET_GODOT", "godot")
GD_DIR = Path(__file__).resolve().parent / "gd"
TEMPLATES_SRC = Path("/opt/godot-data/godot/export_templates")
GODOT_VERSION = "4.4.1"
FIXED_FPS = 30

MAX_ZIP_FILES = 20000
MAX_ZIP_BYTES = 2 * 1024**3


# --------------------------------------------------------------------------- engine process


def godot_env(display: str | None = None) -> dict[str, str]:
    """A writable home for Godot (editor settings, user://) with the export templates linked in."""
    root = Path(tempfile.gettempdir()) / "skillnet-godot-home"
    data = root / "data" / "godot"
    data.mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "cache").mkdir(parents=True, exist_ok=True)
    link = data / "export_templates"
    if TEMPLATES_SRC.is_dir() and not link.exists():
        with contextlib.suppress(FileExistsError):
            link.symlink_to(TEMPLATES_SRC)
    env = {
        "HOME": str(root),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "GALLIUM_DRIVER": "llvmpipe",
    }
    if display:
        env["DISPLAY"] = display
    return env


@dataclass
class ProcResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    seconds: float

    @property
    def text(self) -> str:
        return self.stdout + "\n" + self.stderr


def run_proc(
    ctx: ToolContext,
    args: list[str],
    *,
    timeout_s: float,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> ProcResult:
    """Run a process in its own group; on timeout kill the whole group and report it (no raise)."""
    ctx.check_cancelled()
    remaining = ctx.remaining_s()
    budget = timeout_s if remaining is None else max(1.0, min(timeout_s, remaining - 3))
    started = time.monotonic()
    out_f = tempfile.TemporaryFile()
    err_f = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        stdin=subprocess.DEVNULL,
        stdout=out_f,
        stderr=err_f,
        start_new_session=True,
    )
    ctx.register_process(proc)  # type: ignore[arg-type]
    timed_out = False
    try:
        while proc.poll() is None:
            if ctx.cancelled:
                _killpg(proc)
                ctx.check_cancelled()
            if time.monotonic() - started > budget:
                timed_out = True
                _killpg(proc)
                break
            time.sleep(0.05)
        proc.wait()
    finally:
        ctx.unregister_process(proc)  # type: ignore[arg-type]
        _killpg(proc)
    out_f.seek(0)
    err_f.seek(0)
    stdout = out_f.read().decode("utf-8", "replace")
    stderr = err_f.read().decode("utf-8", "replace")
    out_f.close()
    err_f.close()
    return ProcResult(proc.returncode, stdout, stderr, timed_out, time.monotonic() - started)


def _killpg(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(proc.pid, signal.SIGKILL)


@contextlib.contextmanager
def virtual_display(width: int = 1280, height: int = 720) -> Iterator[str]:
    """Start a private Xvfb server and yield its DISPLAY value."""
    r, w = os.pipe()
    proc = subprocess.Popen(
        ["Xvfb", "-displayfd", str(w), "-screen", "0", f"{max(width, 64)}x{max(height, 64)}x24",
         "-nolisten", "tcp", "-noreset"],
        pass_fds=(w,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    os.close(w)
    try:
        num = b""
        deadline = time.monotonic() + 15
        os.set_blocking(r, False)
        while time.monotonic() < deadline:
            try:
                chunk = os.read(r, 32)
            except BlockingIOError:
                chunk = b""
            if chunk:
                num += chunk
                if b"\n" in num:
                    break
            elif proc.poll() is not None:
                break
            else:
                time.sleep(0.05)
        os.close(r)
        if not num.strip():
            raise ToolError(
                "display_failed",
                "The virtual display could not be started.",
                "Retry the call once; if it fails again, report this to the skill owner.",
            )
        yield ":" + num.decode().strip()
    finally:
        _killpg(proc)
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)


def godot_import(ctx: ToolContext, project: Path, timeout_s: float = 180) -> ProcResult:
    """Import the project's assets and refresh its script class cache (skipped when unchanged)."""
    stamp_file = project / ".godot" / "skillnet_import_stamp"
    fp = project_fingerprint(project)
    if stamp_file.exists() and stamp_file.read_text() == fp:
        return ProcResult(0, "", "", False, 0.0)
    res = run_proc(ctx, [GODOT, "--headless", "--path", str(project), "--import"],
                   timeout_s=timeout_s, env=godot_env())
    if res.timed_out:
        raise ToolError(
            "timeout",
            f"Importing the project's assets took longer than {timeout_s:.0f}s.",
            "Remove very large assets (videos, huge textures) from the project and try again.",
        )
    if (project / ".godot").is_dir():
        stamp_file.write_text(fp)
    return res


def run_gd_script(
    ctx: ToolContext, project: Path, script: str, payload: dict, timeout_s: float = 120
) -> tuple[dict | None, ProcResult]:
    """Run one of the skill's SceneTree scripts (tools/gd) inside the project, headless.

    The script reads its JSON job from argv and writes its JSON result to a file."""
    with tempfile.TemporaryDirectory(prefix="skn-job-") as td:
        job = Path(td) / "job.json"
        out = Path(td) / "result.json"
        payload = {**payload, "result_path": str(out)}
        job.write_text(json.dumps(payload))
        res = run_proc(
            ctx,
            [GODOT, "--headless", "--path", str(project), "--script", str(GD_DIR / script),
             "--", f"--skillnet-job={job}"],
            timeout_s=timeout_s,
            env=godot_env(),
        )
        data = None
        if out.exists():
            try:
                data = json.loads(out.read_text())
            except json.JSONDecodeError:
                data = None
        return data, res


# --------------------------------------------------------------------------- log parsing

_LEVELS = {
    "SCRIPT ERROR": "error",
    "ERROR": "error",
    "USER ERROR": "error",
    "USER SCRIPT ERROR": "error",
    "WARNING": "warning",
    "USER WARNING": "warning",
    "SCRIPT WARNING": "warning",
    "USER SCRIPT WARNING": "warning",
}
_HEAD = re.compile(r"^(USER SCRIPT ERROR|USER SCRIPT WARNING|SCRIPT ERROR|SCRIPT WARNING|USER ERROR|USER WARNING|ERROR|WARNING): (.*)$")
_AT = re.compile(r"^\s+at: (.*?)(?: \((.*)\))?\s*$")
_RES_LINE = re.compile(r"(res://[^\s:\"']+)(?::(\d+))?")
_STEP = re.compile(r"^\[SKN-STEP\] (\d+)")

# Engine noise that is not about the user's project.
_NOISE = (
    "set_use_vsync",
    "Unable to load", "XOpenIM", "Couldn't load the libspeechd",
    "ALSA", "PulseAudio", "pulseaudio", "Audio driver", "audio driver",
    "No such file or directory: /proc", "Your video card drivers", "glXSwapIntervalEXT",
    "_skillnet", "skillnet_", "Condition \"!windows.has(p_window)\"",
    "Could not create directory", "editor_settings", "Editor settings",
    "ObjectDB instances leaked", "resources still in use at exit", "Leaked instance",
    "Orphan StringName", "Pages in use exist at exit",
)


@dataclass
class LogEntry:
    level: str
    message: str
    file: str | None = None
    line: int | None = None
    function: str | None = None
    step: int | None = None

    def as_dict(self) -> dict:
        d: dict = {"message": self.message}
        if self.file:
            d["file"] = self.file
        if self.line is not None:
            d["line"] = self.line
        if self.function:
            d["function"] = self.function
        if self.step is not None:
            d["step"] = self.step
        return d


def parse_log(text: str, keep_noise: bool = False) -> list[LogEntry]:
    entries: list[LogEntry] = []
    lines = text.splitlines()
    step: int | None = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        sm = _STEP.match(ln)
        if sm:
            step = int(sm.group(1))
            i += 1
            continue
        m = _HEAD.match(ln)
        if not m:
            i += 1
            continue
        level = _LEVELS[m.group(1)]
        msg = m.group(2).strip()
        entry = LogEntry(level=level, message=msg[:500], step=step)
        if i + 1 < len(lines):
            am = _AT.match(lines[i + 1])
            if am:
                entry.function = am.group(1).strip()[:120] or None
                loc = am.group(2) or ""
                rm = _RES_LINE.search(loc)
                if rm:
                    entry.file = rm.group(1)
                    entry.line = int(rm.group(2)) if rm.group(2) else None
                i += 1
        if entry.file is None:
            rm = _RES_LINE.search(msg)
            if rm:
                entry.file = rm.group(1)
                entry.line = int(rm.group(2)) if rm.group(2) else None
        if entry.file:
            entry.file = entry.file.rstrip(".,;)")
        if keep_noise or not any(n in msg or n in (entry.function or "") for n in _NOISE):
            entries.append(entry)
        i += 1
    # De-duplicate identical messages (the same error each frame), keeping the first.
    seen: set[tuple] = set()
    unique: list[LogEntry] = []
    for e in entries:
        key = (e.level, e.message, e.file, e.line)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique


def errors_of(entries: list[LogEntry]) -> list[LogEntry]:
    return [e for e in entries if e.level == "error"]


def warnings_of(entries: list[LogEntry]) -> list[LogEntry]:
    return [e for e in entries if e.level == "warning"]


def clean_log(text: str, limit_lines: int | None = None) -> str:
    """Drop engine banner/noise lines for the user-facing log."""
    keep = []
    for ln in text.splitlines():
        if ln.startswith("[SKN-"):
            continue
        if any(n in ln for n in ("set_use_vsync", "gl_manager_x11", "XOpenIM", "_skillnet")):
            continue
        keep.append(ln)
    if limit_lines is not None:
        keep = keep[-limit_lines:]
    return "\n".join(keep)


# --------------------------------------------------------------------------- res:// paths

_BAD_PARTS = {"..", ""}


def res_to_rel(path: str, *, allow_root: bool = False) -> str:
    """Validate a res:// path and return it relative to the project root."""
    p = path.strip()
    if not p.startswith("res://"):
        raise ToolError(
            "invalid_path",
            f"'{path[:120]}' is not a res:// path.",
            "Give project paths starting with res://, for example res://scripts/player.gd.",
        )
    rel = p[len("res://"):].strip("/")
    parts = rel.split("/") if rel else []
    if (not parts and not allow_root) or any(part in _BAD_PARTS or part.startswith(".godot") for part in parts) or "\\" in rel:
        raise ToolError(
            "invalid_path",
            f"'{path[:120]}' points outside the project or into Godot's cache.",
            "Use a res:// path inside the project such as res://scenes/level.tscn (no '..', not .godot/).",
        )
    return rel


def rel_to_res(rel: str) -> str:
    return "res://" + rel.replace(os.sep, "/")


# --------------------------------------------------------------------------- project state

def project_fingerprint(project: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(project.rglob("*")):
        rel = p.relative_to(project)
        if rel.parts and rel.parts[0] == ".godot":
            continue
        if p.is_file():
            st = p.stat()
            h.update(f"{rel}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def project_files(project: Path) -> list[str]:
    out = []
    for p in sorted(project.rglob("*")):
        rel = p.relative_to(project)
        if rel.parts and rel.parts[0] in (".godot",):
            continue
        if p.is_file() and not p.name.endswith(".import") and p.name != ".DS_Store":
            out.append(rel_to_res(str(rel)))
    return out


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_FILES:
        raise ToolError("project_too_large", f"The zip holds {len(infos)} entries (limit {MAX_ZIP_FILES}).",
                        "Remove unused assets and zip only the Godot project folder.")
    total = sum(i.file_size for i in infos)
    if total > MAX_ZIP_BYTES:
        raise ToolError("project_too_large", "The zip unpacks to more than 2 GB.",
                        "Remove large unused assets and zip only the Godot project folder.")
    root = dest.resolve()
    for info in infos:
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            continue
        target = (dest / name).resolve()
        if not target.is_relative_to(root):
            continue
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        # Skip symlinks stored in the zip.
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _find_project_root(base: Path) -> Path | None:
    if (base / "project.godot").is_file():
        return base
    candidates = sorted(base.rglob("project.godot"), key=lambda p: len(p.parts))
    candidates = [c for c in candidates if "__MACOSX" not in c.parts]
    return candidates[0].parent if candidates else None


def config_version(project: Path) -> int | None:
    try:
        text = (project / "project.godot").read_text(errors="replace")
    except OSError:
        return None
    m = re.search(r"^config_version\s*=\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else None


def state_project(ctx: ToolContext) -> Path:
    return ctx.state_dir / "project"


# Godot 3 constructs and the Godot 4 form, appended to parse errors so the fix (and the report) is plain.
GODOT3_HINTS = [
    (re.compile(r'identifier "onready"'), 'Godot 3 syntax: write "@onready var" in Godot 4'),
    (re.compile(r'identifier "export"'), 'Godot 3 syntax: write "@export var" in Godot 4'),
    (re.compile(r'identifier "tool"'), 'Godot 3 syntax: write "@tool" in Godot 4'),
    (re.compile(r'"yield"'), 'Godot 3 syntax: use "await signal" in Godot 4'),
    (re.compile(r'argument for "connect\(\)"|"connect\(\)" function'), 'Godot 3 connect("signal", self, "method"): in Godot 4 write signal_name.connect(method)'),
    (re.compile(r'"emit_signal\(\)"'), 'Godot 3 style: in Godot 4 prefer signal_name.emit(args)'),
    (re.compile(r'"instance\(\)"|function "instance"'), 'Godot 3 name: use instantiate() in Godot 4'),
]


def godot4_hint(message: str) -> str:
    """Append a plain Godot 3 -> 4 hint to an engine message when it matches a known Godot 3 construct."""
    if "Godot 3" in message:
        return message
    for pat, hint in GODOT3_HINTS:
        if pat.search(message):
            return f"{message} ({hint})"
    return message


def load_project(ctx: ToolContext, project_zip: Path | None, *, required: bool = True) -> Path | None:
    """Open the project for this call: an uploaded zip (replaces the state's project) or the state."""
    dest = state_project(ctx)
    if project_zip is not None:
        tmp = Path(tempfile.mkdtemp(prefix="skn-unzip-"))
        try:
            try:
                with zipfile.ZipFile(project_zip) as zf:
                    _safe_extract(zf, tmp)
            except zipfile.BadZipFile:
                raise ToolError("bad_zip", "The project file is not a readable zip archive.",
                                "Zip the Godot project folder (the one containing project.godot) and upload it again.") from None
            root = _find_project_root(tmp)
            if root is None:
                raise ToolError("not_a_godot_project", "The zip has no project.godot file.",
                                "Upload a zip of the Godot project folder that contains project.godot, or start a new game with create_game_project.")
            cv = config_version(root)
            if cv is None or cv < 5:
                raise ToolError("godot3_project",
                                "This is a Godot 3.x (or older) project; the skill works with Godot 4 projects only.",
                                "Ask the user to convert it with the Godot 4 editor's project converter, or rebuild the game with create_game_project.")
            if dest.exists():
                shutil.rmtree(dest)
            (dest.parent / "check_history.json").unlink(missing_ok=True)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root), str(dest))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return dest
    if (dest / "project.godot").is_file():
        return dest
    if not required:
        return None
    raise ToolError(
        "no_project",
        "No game project was given and no earlier project was found for this state.",
        "Pass the state_id returned by create_game_project (or an earlier call), or upload the project zip as `project`.",
    )


def zip_project(project: Path, out: Path) -> Path:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(project.rglob("*")):
            rel = p.relative_to(project)
            if rel.parts and rel.parts[0] == ".godot":
                continue
            if p.is_file():
                zf.write(p, str(rel))
    return out


def work_copy(project: Path) -> Path:
    """A throwaway copy of the project (with its import cache) for runs that inject helpers."""
    dest = Path(tempfile.mkdtemp(prefix="skn-run-")) / "project"
    shutil.copytree(project, dest, symlinks=False)
    return dest


# --------------------------------------------------------------------------- project.godot

def read_project_godot(project: Path) -> dict[str, dict[str, str]]:
    """Parse project.godot into {section: {key: raw value}} (values may span lines)."""
    text = (project / "project.godot").read_text(errors="replace")
    sections: dict[str, dict[str, str]] = {"": {}}
    cur = ""
    buf_key = None
    buf: list[str] = []
    depth = 0

    def depth_of(s: str) -> int:
        d = 0
        in_str = False
        esc = False
        for ch in s:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "{[(":
                d += 1
            elif ch in "}])":
                d -= 1
        return d

    for line in text.splitlines():
        if buf_key is not None:
            buf.append(line)
            depth += depth_of(line)
            if depth <= 0:
                sections[cur][buf_key] = "\n".join(buf)
                buf_key = None
            continue
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]") and "=" not in s:
            cur = s[1:-1]
            sections.setdefault(cur, {})
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            d = depth_of(v)
            if d > 0:
                buf_key = k.strip()
                buf = [v]
                depth = d
            else:
                sections[cur][k.strip()] = v.strip()
    return sections


def unquote(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1].replace('\\"', '"')
    return v


def main_scene_of(project: Path) -> str | None:
    try:
        cfg = read_project_godot(project)
    except OSError:
        return None
    ms = unquote(cfg.get("application", {}).get("run/main_scene"))
    if ms and ms.startswith("uid://"):
        ms = resolve_uid(project, ms) or ms
    return ms


def resolve_uid(project: Path, uid: str) -> str | None:
    """Find the res:// path of a uid:// reference by scanning scene/resource headers and .uid files."""
    pat = re.compile(r'uid="' + re.escape(uid) + '"')
    for p in project.rglob("*"):
        rel = p.relative_to(project)
        if rel.parts and rel.parts[0] == ".godot" or not p.is_file():
            continue
        if p.suffix in (".tscn", ".tres", ".scn"):
            try:
                head = p.read_text(errors="replace").split("\n", 1)[0]
            except OSError:
                continue
            if pat.search(head):
                return rel_to_res(str(rel))
        elif p.suffix == ".uid":
            try:
                if p.read_text().strip() == uid:
                    return rel_to_res(str(rel)[: -len(".uid")])
            except OSError:
                continue
    return None


def renderer_of(project: Path) -> str:
    try:
        cfg = read_project_godot(project)
    except OSError:
        return "unknown"
    r = unquote(cfg.get("rendering", {}).get("renderer/rendering_method"))
    return r or "forward_plus"


def set_main_scene_text(project: Path, res_path: str) -> None:
    """Small text edit used before a run when the agent asks for a specific scene."""
    pg = project / "project.godot"
    text = pg.read_text()
    line = f'run/main_scene="{res_path}"'
    if re.search(r"^run/main_scene=.*$", text, re.M):
        text = re.sub(r"^run/main_scene=.*$", line, text, flags=re.M)
    elif re.search(r"^\[application\]\s*$", text, re.M):
        text = re.sub(r"^\[application\]\s*$", "[application]\n" + line, text, count=1, flags=re.M)
    else:
        text += f"\n[application]\n{line}\n"
    pg.write_text(text)


def add_autoload_text(project: Path, name: str, res_path: str) -> None:
    """Insert an autoload first in the [autoload] section (so it loads before the game's own)."""
    pg = project / "project.godot"
    text = pg.read_text()
    entry = f'{name}="*{res_path}"'
    if re.search(r"^\[autoload\]\s*$", text, re.M):
        text = re.sub(r"^\[autoload\]\s*$", "[autoload]\n\n" + entry, text, count=1, flags=re.M)
    else:
        text += f"\n[autoload]\n\n{entry}\n"
    pg.write_text(text)


def project_name_of(project: Path) -> str:
    try:
        return unquote(read_project_godot(project).get("application", {}).get("config/name")) or "game"
    except OSError:
        return "game"


@dataclass
class Shot:
    t: float
    file: str
    mean_color: str
    blank: bool
    rgb: list[int] = field(default_factory=list)


def analyze_png(path: Path) -> tuple[list[int], str, bool, str, float]:
    """Mean colour, blank flag, and the most common exact pixel colour with its share of the frame."""
    from PIL import Image, ImageStat

    with Image.open(path) as im:
        rgb = im.convert("RGB")
        small = rgb.resize((min(256, rgb.width), min(256, rgb.height)))
        st = ImageStat.Stat(small)
        mean = [int(round(v)) for v in st.mean]
        spread = max(st.stddev)
        hexc = "#%02x%02x%02x" % tuple(mean)
        total = rgb.width * rgb.height
        colors = rgb.getcolors(maxcolors=total) or []
        count, dom = max(colors, key=lambda c: c[0]) if colors else (0, (0, 0, 0))
        return mean, hexc, spread < 1.5, "#%02x%02x%02x" % tuple(dom), round(count / max(total, 1), 3)


def contact_sheet(images: list[tuple[str, Path]], out: Path, thumb_w: int = 384) -> Path | None:
    from PIL import Image, ImageDraw

    if not images:
        return None
    thumbs = []
    for label, p in images:
        with Image.open(p) as im:
            im = im.convert("RGB")
            h = max(1, int(im.height * thumb_w / im.width))
            thumbs.append((label, im.resize((thumb_w, h))))
    cols = min(3, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    th = max(t.height for _, t in thumbs)
    pad, label_h = 6, 18
    sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (th + label_h + pad) + pad), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for i, (label, t) in enumerate(thumbs):
        x = pad + (i % cols) * (thumb_w + pad)
        y = pad + (i // cols) * (th + label_h + pad)
        draw.text((x + 2, y + 2), label[:60], fill=(230, 230, 230))
        sheet.paste(t, (x, y + label_h))
    sheet.save(out)
    return out
