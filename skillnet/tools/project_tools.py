"""Start, shape and understand a Godot project: create, write files, edit scenes, inspect."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from pydantic import Field

from skillnet_sdk import FileConstraints, InputFile, OutputFile, ToolContext, ToolError, ToolInput, ToolOutput, ToolResult, tool

from . import common as C
from . import scan
from .starters import INPUT_ACTIONS, build_starter

ProjectZip = Annotated[InputFile, FileConstraints(extensions=[".zip"])]
STATE_V = 1

TEXT_EXT = {".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc", ".shader", ".cfg", ".json", ".txt", ".md",
            ".csv", ".godot", ".ini", ".gitignore", ".svg", ".import"}


class ScriptError(ToolOutput):
    path: str
    line: Optional[int] = None
    message: str


def _parse_with_context(text: str) -> list[dict]:
    """Parse a checker log, attributing file-less messages to the file being checked."""
    out = []
    current = None
    chunk: list[str] = []

    def flush() -> None:
        for e in C.parse_log("\n".join(chunk)):
            d = e.as_dict()
            if not d.get("file") and current:
                d["file"] = current
            d["level"] = e.level
            out.append(d)

    for ln in text.splitlines():
        if ln.startswith("[SKN-FILE] "):
            flush()
            chunk = []
            current = ln[len("[SKN-FILE] "):].strip()
        else:
            chunk.append(ln)
    flush()
    seen = set()
    uniq = []
    for d in out:
        k = (d["level"], d["message"], d.get("file"), d.get("line"))
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


def run_checker(ctx: ToolContext, project: Path, scripts: list[str], scenes: list[str]) -> tuple[list[dict], list[dict], dict | None]:
    imp = C.godot_import(ctx, project)
    raw, res = C.run_gd_script(ctx, project, "check.gd", {"scripts": scripts, "scenes": scenes}, timeout_s=150)
    if res.timed_out:
        raise ToolError("timeout", "Checking the project's scripts took too long and was stopped.",
                        "A script may loop forever in _init() or static code; find and fix it with write_game_files.")
    found = _parse_with_context(res.stderr)
    imp_found = [dict(d, level=e.level) for e in C.parse_log(imp.stderr + "\n" + imp.stdout) for d in [e.as_dict()]]
    errs = [d for d in found if d["level"] == "error"]
    warns = [d for d in found if d["level"] == "warning"]
    for d in imp_found:
        if d["level"] == "error" and not any(x["message"] == d["message"] for x in errs):
            errs.append(d)
    # A parse error with a line already explains the follow-up "Failed to load script ... Parse error" lines.
    precise = {d.get("file") for d in errs if d.get("line") and d["message"].startswith("Parse Error")}
    errs = [d for d in errs if not (d.get("file") in precise and not d.get("line")
                                    and "Failed to load script" in d["message"])]
    for lst in (errs, warns):
        for d in lst:
            d.pop("level", None)
    if raw is None:
        errs.append({"message": "the checker stopped before finishing (exit %s)" % res.returncode})
    return errs, warns, raw


def finish_project_outputs(ctx: ToolContext, project: Path) -> list[OutputFile]:
    z = C.zip_project(project, ctx.output_path("project.zip"))
    return [OutputFile(z, "The Godot 4 project (open project.godot in Godot 4.4, or pass this zip back to any tool).")]


# =============================================================================== create

class CreateIn(ToolInput):
    name: str = Field(description="The game's title, e.g. 'Coin Dash'. Used as the project name and window title.", min_length=1, max_length=60)
    starter: Literal["blank_2d", "top_down", "platformer", "blank_3d"] = Field(
        default="top_down",
        description="Starting point: top_down (8-way movement, coins, score), platformer (side view with gravity, jump, ledges, coins; "
                    "'side-scroller' or 'jump and run' means platformer), blank_2d (empty 2D scene with a title), blank_3d (3D arena with a capsule player).")
    window_width: int = Field(default=1152, ge=320, le=3840, description="Game window width in pixels.")
    window_height: int = Field(default=648, ge=240, le=2160, description="Game window height in pixels.")


class CreateOut(ToolOutput):
    project_name: str
    starter: str
    main_scene: str
    files: list[str]
    input_actions: dict[str, list[str]]
    starts_cleanly: bool
    errors: list[dict] = Field(default_factory=list)


@tool(kind="create", title="Start a new Godot game project", timeout_s=180, state_version=STATE_V,
      examples=[{"arguments": {"name": "Coin Dash", "starter": "top_down"}}])
def create_game_project(args: CreateIn, ctx: ToolContext) -> ToolResult[CreateOut]:
    """Start here when the user describes a new game. Creates a Godot 4.4 project from a starter (top_down, platformer, blank_2d, blank_3d) with a main scene, a player with movement code, coins and a score label (2D starters), input actions move_left/right/up/down, jump, pause, and the software-safe renderer, then imports and runs it headlessly to prove it starts. Returns a state_id to pass to every later call, the project zip and its file list. Next: write_game_files / edit_scenes, then check_project."""
    name = args.name.strip()
    if not re.search(r"[A-Za-z0-9]", name) or any(c in name for c in '\n\r\t"\\'):
        raise ToolError("invalid_name", "The game name must contain letters or digits and no quotes, backslashes or line breaks.",
                        "Call again with a plain title such as 'Coin Dash'.")
    project = C.state_project(ctx)
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)
    ctx.progress(10, "writing starter files")
    for rel, text in build_starter(args.starter, name, args.window_width, args.window_height).items():
        p = project / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    ctx.progress(30, "importing the project")
    scripts = [C.rel_to_res(str(p.relative_to(project))) for p in scan.list_files(project, (".gd",))]
    scenes = [C.rel_to_res(str(p.relative_to(project))) for p in scan.list_files(project, (".tscn",))]
    errs, _warns, _raw = run_checker(ctx, project, scripts, scenes)
    ctx.progress(70, "running the main scene headlessly")
    res = C.run_proc(ctx, [C.GODOT, "--headless", "--path", str(project), "--audio-driver", "Dummy",
                           "--fixed-fps", "30", "--quit-after", "45"], timeout_s=60, env=C.godot_env())
    run_errs = [e.as_dict() for e in C.errors_of(C.parse_log(res.stderr))]
    clean = not errs and not run_errs and not res.timed_out and res.returncode == 0
    out = CreateOut(project_name=name, starter=args.starter, main_scene="res://scenes/main.tscn",
                    files=C.project_files(project), input_actions={k: v for k, v in INPUT_ACTIONS.items()},
                    starts_cleanly=clean, errors=(errs + run_errs)[:20])
    outputs = finish_project_outputs(ctx, project)
    if not clean:
        return ToolResult(data=out, status="partial", summary=f"Created '{name}' ({args.starter}) but its first run reported errors",
                          outputs=outputs, uncertain=["The starter did not start cleanly; see errors."],
                          next_step="Report this to the skill owner; meanwhile try another starter.")
    return ToolResult(
        data=out, outputs=outputs,
        summary=f"Created '{name}' from the {args.starter} starter; it imports and starts cleanly",
        next_step="Keep the state_id. Add game logic with write_game_files and nodes with edit_scenes, then check_project, run_game and playtest_game.",
    )


# =============================================================================== write files

class FileSpec(ToolInput):
    path: str = Field(description="Project path starting with res://, e.g. res://scripts/enemy.gd or res://scenes/level.tscn.")
    content: str = Field(description="The full text of the file (GDScript for .gd, Godot text scene format for .tscn).", max_length=1_000_000)


class WriteIn(ToolInput):
    project: Optional[ProjectZip] = Field(default=None, description="An existing Godot 4 project as a zip, to open it when there is no state_id yet (replaces the state's project).")
    files: list[FileSpec] = Field(default_factory=list, max_length=50, description="Files to write or replace (up to 50). Text files only: .gd, .tscn, .tres, .gdshader, .cfg, .json, .txt, .md, .csv, project.godot.")
    delete: list[str] = Field(default_factory=list, max_length=100, description="res:// paths of files to delete.")


class WriteOut(ToolOutput):
    written: list[str]
    deleted: list[str]
    script_errors: list[ScriptError]
    scene_problems: list[str] = Field(default_factory=list)
    ok: bool
    files: list[str]


@tool(kind="edit", title="Write or replace game scripts and scenes", timeout_s=240, state_version=STATE_V,
      examples=[{"arguments": {"files": [{"path": "res://scripts/enemy.gd", "content": "extends Area2D\n"}]}}])
def write_game_files(args: WriteIn, ctx: ToolContext) -> ToolResult[WriteOut]:
    """Use to add game logic or fix code that check_project flagged: writes GDScript (.gd), scenes (.tscn), resources (.tres), shaders or text files at res:// paths, can delete files, and compiles every written .gd with Godot 4.4 right away, returning syntax errors with line numbers. Also opens an uploaded project zip when there is no state_id yet. Returns the updated project zip and state_id; files are written even when they have errors, so fix and call again."""
    project = C.load_project(ctx, args.project)
    assert project is not None
    if not args.files and not args.delete and args.project is None:
        raise ToolError("nothing_to_do", "No files to write or delete were given.",
                        "Pass `files` as a list of {path: 'res://...', content: '...'} or `delete` as res:// paths.")
    written, deleted = [], []
    plan: list[tuple[str, Path, str]] = []
    for f in args.files:
        rel = C.res_to_rel(f.path)
        suffix = Path(rel).suffix.lower() or Path(rel).name
        if suffix not in TEXT_EXT and Path(rel).name != "project.godot":
            raise ToolError("unsupported_file_type", f"{f.path} is not a text file type this tool writes.",
                            "Write only .gd, .tscn, .tres, .gdshader, .cfg, .json, .txt, .md or .csv files; images and audio can't be added (the skill uses shapes and colours).")
        if rel == "project.godot" and not re.search(r"^config_version\s*=\s*5", f.content, re.M):
            raise ToolError("bad_project_file", "The new project.godot lacks config_version=5 (Godot 4).",
                            "Keep 'config_version=5' at the top of project.godot, or change settings with edit_scenes set_setting instead.")
        plan.append((f.path, project / rel, f.content))
    for d in args.delete:
        rel = C.res_to_rel(d)
        if rel == "project.godot":
            raise ToolError("invalid_path", "project.godot can't be deleted.", "Delete other files only.")
        p = project / rel
        if p.is_file():
            p.unlink()
            for extra in (p.with_name(p.name + ".uid"), p.with_name(p.name + ".import")):
                if extra.exists():
                    extra.unlink()
            deleted.append(C.rel_to_res(rel))
        elif p.is_dir():
            shutil.rmtree(p)
            deleted.append(C.rel_to_res(rel))
    for res_path, p, content in plan:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        written.append(C.rel_to_res(str(p.relative_to(project))))
    ctx.progress(30, "compiling scripts")
    gd = [w for w in written if w.endswith(".gd")]
    tscn = [w for w in written if w.endswith(".tscn")]
    errors: list[dict] = []
    scene_problems: list[str] = []
    if gd or tscn:
        errs, _warns, raw = run_checker(ctx, project, gd, tscn)
        errors = [e for e in errs if e.get("file") in set(gd + tscn) or not e.get("file")]
        if raw:
            for s in raw.get("scenes", []):
                scene_problems += [f"{s['path']}: {p}" for p in s.get("problems", [])]
            for s in raw.get("scripts", []):
                if not s.get("ok") and not any(e.get("file") == s["path"] for e in errors):
                    errors.append({"file": s["path"], "message": "the script failed to compile"})
    script_errors = [ScriptError(path=e.get("file") or "?", line=e.get("line"), message=e["message"]) for e in errors][:40]
    ok = not script_errors and not scene_problems
    out = WriteOut(written=written, deleted=deleted, script_errors=script_errors, scene_problems=scene_problems[:30], ok=ok,
                   files=C.project_files(project)[:200])
    outputs = finish_project_outputs(ctx, project)
    if args.project is not None and not written and not deleted:
        return ToolResult(data=out, outputs=outputs, summary=f"Opened project '{C.project_name_of(project)}'",
                          next_step="Call inspect_project to see its structure, or check_project to find errors.")
    if not ok:
        n = len(script_errors) + len(scene_problems)
        return ToolResult(data=out, outputs=outputs,
                          summary=f"Wrote {len(written)} file(s); {n} problem(s) found",
                          next_step="Fix each script_errors entry (file and line) and write the corrected file again with write_game_files. Godot 3 syntax (onready, yield, KinematicBody2D, export var) must be converted to Godot 4.")
    return ToolResult(data=out, outputs=outputs,
                      summary=f"Wrote {len(written)} and deleted {len(deleted)} file(s); all written scripts compile",
                      next_step="Run check_project, then run_game or playtest_game.")


# =============================================================================== edit scenes

OpName = Literal["create_scene", "add_node", "remove_node", "rename_node", "reparent_node", "set_properties",
                 "attach_script", "instantiate_scene", "connect_signal", "add_to_group", "set_collision_layers",
                 "add_input_action", "set_autoload", "set_main_scene", "set_setting"]

REQUIRED: dict[str, tuple[str, ...]] = {
    "create_scene": ("scene",), "add_node": ("scene", "type"), "remove_node": ("scene", "node"),
    "rename_node": ("scene", "node", "name"), "reparent_node": ("scene", "node", "parent"),
    "set_properties": ("scene", "properties"), "attach_script": ("scene", "script"),
    "instantiate_scene": ("scene", "child_scene"), "connect_signal": ("scene", "node", "signal", "method"),
    "add_to_group": ("scene", "node", "groups"), "set_collision_layers": ("scene", "node"),
    "add_input_action": ("name", "keys"), "set_autoload": ("name",), "set_main_scene": ("scene",),
    "set_setting": ("setting",),
}


class SceneOp(ToolInput):
    op: OpName = Field(description="The operation (see the tool description for what each needs).")
    scene: Optional[str] = Field(default=None, description="res:// path of the .tscn to edit (or to create / make main).")
    node: Optional[str] = Field(default=None, description="Node path relative to the scene root ('.' is the root, 'Player/Sprite' a child). For connect_signal: the node that emits.")
    parent: Optional[str] = Field(default=None, description="Parent node path for add_node / instantiate_scene, or the new parent for reparent_node (default '.').")
    target: Optional[str] = Field(default=None, description="connect_signal: node whose method is called (default '.', the root).")
    type: Optional[str] = Field(default=None, description="Godot class for add_node or the root of create_scene, e.g. CharacterBody2D, Area2D, Sprite2D, Label, Timer, Node3D.")
    name: Optional[str] = Field(default=None, description="New node name (add_node, create_scene root, instantiate_scene, rename_node), input action name, or autoload name.")
    properties: Optional[dict[str, Any]] = Field(default=None, description="Property values: arrays become Vector2/Vector3/Color ([x,y], [x,y,z], [r,g,b,a]); colours also as '#rrggbb' or 'red'; resources as 'res://...' or {\"type\": \"RectangleShape2D\", \"size\": [32,32]}.")
    script: Optional[str] = Field(default=None, description="res:// path of a .gd script (attach_script, add_node, create_scene, set_autoload).")
    child_scene: Optional[str] = Field(default=None, description="instantiate_scene: res:// path of the scene to place inside `scene`.")
    signal: Optional[str] = Field(default=None, description="connect_signal: signal name, e.g. body_entered, timeout, pressed.")
    method: Optional[str] = Field(default=None, description="connect_signal: method name on the target, e.g. _on_coin_body_entered.")
    groups: Optional[list[str]] = Field(default=None, description="add_to_group (or add_node / instantiate_scene): group names.")
    layers: Optional[list[int]] = Field(default=None, description="set_collision_layers: layer numbers 1-32 the node is on.")
    mask: Optional[list[int]] = Field(default=None, description="set_collision_layers: layer numbers 1-32 the node detects.")
    keys: Optional[list[str]] = Field(default=None, description="add_input_action: key names (A, Space, Enter, Escape, Left, Up, Shift...) or mouse_left / mouse_right / mouse_middle.")
    remove: bool = Field(default=False, description="set_autoload: remove the autoload instead of adding it.")
    setting: Optional[str] = Field(default=None, description="set_setting: project setting path, e.g. display/window/size/viewport_width or physics/2d/default_gravity.")
    value: Optional[Any] = Field(default=None, description="set_setting: the new value.")


class EditIn(ToolInput):
    operations: list[SceneOp] = Field(min_length=1, max_length=100, description="Operations applied in order (up to 100). Nothing is saved if any operation fails.")


class OpResult(ToolOutput):
    op: str
    ok: bool
    message: str


class EditOut(ToolOutput):
    applied: int
    failed_op: Optional[int]
    results: list[OpResult]
    scenes_changed: list[str]


def _norm_op(i: int, op: SceneOp) -> dict:
    d = {k: v for k, v in op.model_dump().items() if v is not None}
    missing = [f for f in REQUIRED[op.op] if d.get(f) in (None, "", [])]
    if op.op == "set_autoload" and not op.remove and not op.script:
        missing.append("script")
    if missing:
        raise ToolError("invalid_operation", f"Operation {i} ({op.op}) is missing: {', '.join(missing)}.",
                        f"Add {', '.join(missing)} to operation {i} and call edit_scenes again.")
    for key in ("scene", "script", "child_scene"):
        if key in d:
            d[key] = "res://" + C.res_to_rel(d[key])
    if "scene" in d and op.op != "set_main_scene" and not d["scene"].endswith((".tscn", ".scn")):
        raise ToolError("invalid_operation", f"Operation {i}: {d['scene']} is not a .tscn scene path.",
                        "Use a scene path ending in .tscn, e.g. res://scenes/level.tscn.")
    if op.op in ("add_input_action", "set_autoload") and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", op.name or ""):
        raise ToolError("invalid_operation", f"Operation {i}: '{op.name}' is not a valid name (letters, digits, underscore).",
                        "Use a name such as move_left or GameState.")
    for lst in (op.layers or []) + (op.mask or []):
        if not 1 <= lst <= 32:
            raise ToolError("invalid_operation", f"Operation {i}: collision layer {lst} is outside 1-32.", "Use layer numbers from 1 to 32.")
    return d


@tool(kind="edit", title="Edit scenes and project settings", timeout_s=240, state_version=STATE_V,
      examples=[{"arguments": {"operations": [{"op": "add_node", "scene": "res://scenes/main.tscn", "parent": ".", "type": "Timer", "name": "SpawnTimer", "properties": {"wait_time": 2, "autostart": True}}]}}])
def edit_scenes(args: EditIn, ctx: ToolContext) -> ToolResult[EditOut]:
    """Use to build or change scenes without hand-writing .tscn text; needs a state_id. Runs a batch through Godot's own scene API: create_scene, add_node, remove_node, rename_node, reparent_node, set_properties, attach_script, instantiate_scene, connect_signal, add_to_group, set_collision_layers, and project ops add_input_action, set_autoload, set_main_scene, set_setting. Stops at the first failing op and saves nothing then. Returns each op's result, the updated project zip and state_id."""
    project = C.load_project(ctx, None)
    assert project is not None
    ops = [_norm_op(i, op) for i, op in enumerate(args.operations)]
    work = C.work_copy(project)
    try:
        C.godot_import(ctx, work)
        ctx.progress(30, f"applying {len(ops)} operation(s)")
        raw, res = C.run_gd_script(ctx, work, "scene_ops.gd", {"operations": ops}, timeout_s=180)
        if res.timed_out:
            raise ToolError("timeout", "Applying the scene operations took too long and was stopped.",
                            "Split the operations into smaller batches; a script attached to a node may loop forever in _init().")
        if raw is None:
            errs = C.errors_of(C.parse_log(res.stderr))
            raise ToolError("edit_failed", "The scene editor stopped before finishing" + (f": {errs[0].message}" if errs else "."),
                            "Run check_project to find broken scripts or scenes, fix them with write_game_files, then retry.")
        results = [OpResult(**r) for r in raw["results"]]
        failed = raw["failed_op"] if raw["failed_op"] >= 0 else None
        if failed is None:
            # Commit: copy the edited files back (not the import cache).
            for p in sorted(work.rglob("*")):
                rel = p.relative_to(work)
                if rel.parts and rel.parts[0] == ".godot" or not p.is_file():
                    continue
                dst = project / rel
                if not dst.exists() or dst.read_bytes() != p.read_bytes():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dst)
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
    out = EditOut(applied=len(results) if failed is None else failed, failed_op=failed, results=results,
                  scenes_changed=raw["scenes_changed"] if failed is None else [])
    outputs = finish_project_outputs(ctx, project)
    if failed is not None:
        msg = results[failed].message
        return ToolResult(data=out, outputs=outputs, status="partial",
                          summary=f"Operation {failed} ({results[failed].op}) failed: {msg[:160]}; nothing was saved",
                          uncertain=[f"Operations before {failed} succeeded in a trial run but were not saved."],
                          next_step=f"Fix operation {failed} using its message, then send the whole batch again.")
    return ToolResult(data=out, outputs=outputs, summary=f"Applied {len(results)} operation(s); changed {len(out.scenes_changed)} file(s)",
                      next_step="Run check_project, then run_game to see the result.")


# =============================================================================== inspect

class InspectIn(ToolInput):
    project: Optional[ProjectZip] = Field(default=None, description="The user's Godot 4 project as a zip (opens it and returns a state_id). Omit when passing a state_id.")
    detail: Literal["summary", "full"] = Field(default="summary", description="summary: counts, scripts and actions; full: also every scene's node tree (written to project_map.json either way).")


class SceneInfo(ToolOutput):
    path: str
    root_type: str
    node_count: int
    tree: Optional[list[str]] = None


class ScriptInfo(ToolOutput):
    path: str
    extends: Optional[str]
    class_name: Optional[str] = None
    methods: list[str]
    signals: list[str]
    exports: list[str]


class InspectOut(ToolOutput):
    project_name: str
    config_version: Optional[int]
    renderer: str
    main_scene: Optional[str]
    scenes: list[SceneInfo]
    scripts: list[ScriptInfo]
    input_actions: dict[str, list[str]]
    autoloads: dict[str, str]
    file_count: int


@tool(kind="inspect", title="Summarise a Godot project", timeout_s=90, state_version=STATE_V,
      examples=[{"arguments": {"detail": "summary"}}])
def inspect_project(args: InspectIn, ctx: ToolContext) -> ToolResult[InspectOut]:
    """Use first on a Godot project the user uploads, or before play-testing, to learn its structure: Godot config version and renderer, main scene, scene trees (node names, types, scripts), each script's methods, signals and exported variables, input actions with their keys, and autoloads. Accepts a project zip (opens it and returns a state_id) or a state_id. Reads the files directly, so it also works on projects that don't compile."""
    project = C.load_project(ctx, args.project)
    assert project is not None
    uncertain: list[str] = []
    cfg_v = C.config_version(project)
    try:
        actions = scan.input_actions(project)
        autos = scan.autoloads(project)
    except Exception:  # noqa: BLE001 - malformed project.godot
        actions, autos = {}, {}
        uncertain.append("project.godot could not be fully read; input actions and autoloads may be missing.")
    scenes: list[SceneInfo] = []
    full_map: dict = {"scenes": {}, "scripts": {}}
    for sp in scan.list_files(project, (".tscn",))[:300]:
        res_path = C.rel_to_res(str(sp.relative_to(project)))
        try:
            parsed = scan.parse_tscn(sp, project)
        except Exception:  # noqa: BLE001
            uncertain.append(f"{res_path} could not be read.")
            continue
        nodes = parsed["nodes"]
        tree = []
        for n in nodes:
            depth = 0 if n["path"] == "." else n["path"].count("/") + 1
            extra = f" [{n['script']}]" if n.get("script") else ""
            extra += f" groups={n['groups']}" if n.get("groups") else ""
            tree.append(f"{'  ' * depth}{n['name']} ({n['type']}){extra}")
        full_map["scenes"][res_path] = {"nodes": nodes, "connections": parsed["connections"]}
        scenes.append(SceneInfo(path=res_path, root_type=nodes[0]["type"] if nodes else "?", node_count=len(nodes),
                                tree=tree[:80] if args.detail == "full" else None))
    scripts: list[ScriptInfo] = []
    for gp in scan.list_files(project, (".gd",))[:300]:
        res_path = C.rel_to_res(str(gp.relative_to(project)))
        info = scan.parse_script(gp)
        full_map["scripts"][res_path] = info
        scripts.append(ScriptInfo(path=res_path, extends=info["extends"], class_name=info["class_name"],
                                  methods=info["methods"][:40], signals=info["signals"][:20], exports=info["exports"][:20]))
    if any(p.suffix == ".cs" for p in scan.list_files(project, (".cs",))):
        uncertain.append("The project contains C# scripts; this skill runs GDScript only, so C# parts won't work.")
    main = C.main_scene_of(project)
    if main and not (project / main.replace("res://", "")).exists():
        uncertain.append(f"The main scene {main} does not exist.")
    renderer = C.renderer_of(project)
    if renderer != "gl_compatibility":
        uncertain.append(f"The project uses the {renderer} renderer; runs here use the Compatibility (OpenGL) renderer, so visuals may differ.")
    out = InspectOut(project_name=C.project_name_of(project), config_version=cfg_v, renderer=renderer, main_scene=main,
                     scenes=scenes, scripts=scripts, input_actions=actions, autoloads=autos, file_count=len(C.project_files(project)))
    full_map.update({"project_name": out.project_name, "main_scene": main, "input_actions": actions, "autoloads": autos, "renderer": renderer})
    mp = ctx.output_path("project_map.json")
    mp.write_text(json.dumps(full_map, indent=1))
    ctx.mark_untrusted("project files")
    return ToolResult(
        data=out, outputs=[OutputFile(mp, "Full project map: every scene's nodes and connections, every script's members.")],
        summary=f"'{out.project_name}': {len(scenes)} scene(s), {len(scripts)} script(s), {len(actions)} input action(s), main scene {main or 'not set'}",
        uncertain=uncertain,
        next_step="Pass the state_id to later calls. Use the input action names and node paths shown here in playtest_game steps.",
    )
