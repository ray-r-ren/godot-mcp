"""Check a project for errors, and export playable builds."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field

from skillnet_sdk import OutputFile, ToolContext, ToolError, ToolInput, ToolOutput, ToolResult, tool

from . import common as C
from . import scan
from .project_tools import STATE_V, ProjectZip, run_checker


class Problem(ToolOutput):
    file: Optional[str] = None
    line: Optional[int] = None
    message: str


class CheckIn(ToolInput):
    project: Optional[ProjectZip] = Field(default=None, description="A Godot 4 project zip to check (opens it and returns a state_id). Omit when passing a state_id.")


class CheckOut(ToolOutput):
    verdict: Literal["ready", "has_errors"]
    errors: list[Problem]
    warnings: list[Problem]
    scripts_checked: int
    scenes_checked: int
    main_scene: Optional[str]


def _p(d: dict) -> Problem:
    return Problem(file=d.get("file"), line=d.get("line"), message=str(d.get("message", ""))[:400])


@tool(kind="check", title="Check a game project for errors", timeout_s=300, state_version=STATE_V,
      examples=[{"arguments": {}}])
def check_project(args: CheckIn, ctx: ToolContext) -> ToolResult[CheckOut]:
    """Use after any change and before running: imports the project headlessly with Godot 4.4, compiles every GDScript, loads every scene and reports missing scripts or resources, broken signal connections, a missing or bad main scene, and engine errors with file and line. Works on a state_id or an uploaded project zip. The verdict 'ready' means run_game can be tried; 'has_errors' lists what to fix with write_game_files or edit_scenes."""
    project = C.load_project(ctx, args.project)
    assert project is not None
    errors: list[dict] = []
    warnings: list[dict] = []
    main = C.main_scene_of(project)
    if not main:
        errors.append({"file": "res://project.godot", "message": "no main scene is set (application/run/main_scene)"})
    elif not main.startswith("res://") or not (project / main[6:]).is_file():
        errors.append({"file": "res://project.godot", "message": f"the main scene {main} does not exist"})
    gd_files = scan.list_files(project, (".gd",))
    scene_files = scan.list_files(project, (".tscn",))
    errors += scan.missing_references(project, scene_files)
    if scan.list_files(project, (".cs",)):
        warnings.append({"message": "C# scripts found; this skill runs GDScript only, C# parts are not checked or run"})
    if C.renderer_of(project) != "gl_compatibility":
        warnings.append({"file": "res://project.godot", "message": f"renderer is {C.renderer_of(project)}; runs here use the Compatibility renderer"})
    ctx.progress(20, f"compiling {len(gd_files)} scripts and loading {len(scene_files)} scenes")
    scripts = [C.rel_to_res(str(p.relative_to(project))) for p in gd_files]
    scenes = [C.rel_to_res(str(p.relative_to(project))) for p in scene_files]
    errs, warns, raw = run_checker(ctx, project, scripts, scenes)
    # Drop engine duplicates of missing references we already reported.
    missing = {e["message"].split(" ")[1] for e in errors if e["message"].startswith("references ")}
    for e in errs:
        if any(m in e.get("message", "") for m in missing) and "Parse Error" not in e.get("message", ""):
            continue
        errors.append(e)
    warnings += warns
    if raw:
        for s in raw.get("scenes", []):
            for prob in s.get("problems", []):
                if not any(prob in str(e.get("message")) for e in errors):
                    errors.append({"file": s["path"], "message": prob})
        for s in raw.get("scripts", []):
            if not s.get("ok") and not any(e.get("file") == s["path"] for e in errors):
                errors.append({"file": s["path"], "message": "the script failed to compile"})
    verdict = "ready" if not errors else "has_errors"
    report = ctx.output_path("check_report.json")
    report.write_text(json.dumps({"verdict": verdict, "errors": errors, "warnings": warnings, "main_scene": main,
                                  "scripts": raw.get("scripts") if raw else None, "scenes": raw.get("scenes") if raw else None}, indent=1))
    ctx.mark_untrusted("engine output")
    out = CheckOut(verdict=verdict, errors=[_p(e) for e in errors[:40]], warnings=[_p(w) for w in warnings[:20]],
                   scripts_checked=len(scripts), scenes_checked=len(scenes), main_scene=main)
    uncertain = []
    if len(errors) > 40:
        uncertain.append(f"{len(errors)} errors found; the first 40 are listed, all are in check_report.json.")
    if verdict == "ready":
        return ToolResult(data=out, outputs=[OutputFile(report, "Full check report")], uncertain=uncertain,
                          summary=f"Ready: {len(scripts)} scripts and {len(scenes)} scenes load without errors",
                          next_step="Call run_game to see it running, then playtest_game to check the gameplay.")
    return ToolResult(data=out, outputs=[OutputFile(report, "Full check report")], uncertain=uncertain,
                      summary=f"{len(errors)} error(s) found in {len({e.get('file') for e in errors})} file(s)",
                      next_step="Fix the errors (file and line given) with write_game_files or edit_scenes, then call check_project again.")


# =============================================================================== export

class ExportIn(ToolInput):
    project: Optional[ProjectZip] = Field(default=None, description="A Godot 4 project zip to export (omit when passing a state_id).")
    target: Literal["web", "linux"] = Field(default="web", description="web: HTML5 build that plays in a browser from any static web host ('browser' or 'HTML5' means web); linux: x86_64 Linux executable plus .pck.")
    debug: bool = Field(default=False, description="Export a debug build (prints errors to the console) instead of a release build.")


class BuiltFile(ToolOutput):
    name: str
    bytes: int


class ExportOut(ToolOutput):
    target: str
    files: list[BuiltFile]
    smoke_ok: Optional[bool]
    errors: list[str]


WEB_PRESET = """[preset.0]

name="Web"
platform="Web"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter="_skillnet/*"
export_path="{path}"

[preset.0.options]

custom_template/debug=""
custom_template/release=""
variant/extensions_support=false
variant/thread_support=false
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/export_icon=true
html/custom_html_shell=""
html/head_include=""
html/canvas_resize_policy=2
html/focus_canvas_on_start=true
html/experimental_virtual_keyboard=false
progressive_web_app/enabled=false
"""

LINUX_PRESET = """[preset.0]

name="Linux"
platform="Linux"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter="_skillnet/*"
export_path="{path}"

[preset.0.options]

custom_template/debug=""
custom_template/release=""
debug/export_console_wrapper=0
binary_format/embed_pck=false
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
binary_format/architecture="x86_64"
"""


@tool(kind="export", title="Export a playable Linux or Web build", timeout_s=600, long_running=True, state_version=STATE_V,
      examples=[{"arguments": {"target": "web"}}])
def export_game(args: ExportIn, ctx: ToolContext) -> ToolResult[ExportOut]:
    """Use when the user wants a build to play or share: exports the project with the installed Godot 4.4.1 templates to 'web' (single-threaded HTML5 build that plays from any static web host or itch.io) or 'linux' (x86_64 executable plus .pck). Checks the build files exist and, for Linux, runs the exported game headlessly for 2 seconds as a smoke test. Returns one zip of the build. Run check_project first; Windows, macOS and mobile exports are not available."""
    project = C.load_project(ctx, args.project)
    assert project is not None
    main = C.main_scene_of(project)
    if not main or not (project / main.replace("res://", "")).is_file():
        raise ToolError("no_main_scene", "The project has no valid main scene, so it can't be exported.",
                        "Set one with edit_scenes (op set_main_scene), then run check_project and export again.")
    work = C.work_copy(project)
    build = Path(tempfile.mkdtemp(prefix="skn-build-"))
    uncertain: list[str] = []
    try:
        ctx.progress(10, "importing the project")
        C.godot_import(ctx, work)
        stem = "index" if args.target == "web" else _slug(C.project_name_of(project))
        out_path = build / (f"{stem}.html" if args.target == "web" else f"{stem}.x86_64")
        preset = (WEB_PRESET if args.target == "web" else LINUX_PRESET).format(path=str(out_path))
        (work / "export_presets.cfg").write_text(preset)
        ctx.progress(30, f"exporting the {args.target} build")
        mode = "--export-debug" if args.debug else "--export-release"
        res = C.run_proc(ctx, [C.GODOT, "--headless", "--path", str(work), mode, "Web" if args.target == "web" else "Linux", str(out_path)],
                         timeout_s=480, env=C.godot_env())
        entries = C.parse_log(res.stderr + "\n" + res.stdout)
        errs = [e.message for e in C.errors_of(entries)]
        files = sorted(p for p in build.iterdir() if p.is_file())
        expected = ([build / "index.html", build / "index.wasm", build / "index.pck", build / "index.js"]
                    if args.target == "web" else [out_path, out_path.with_suffix(".pck")])
        missing = [p.name for p in expected if not p.exists()]
        if res.timed_out or missing:
            raise ToolError("export_failed",
                            "The export did not produce " + (", ".join(missing) if missing else "a build in time")
                            + (f": {errs[0][:200]}" if errs else "."),
                            "Run check_project and fix its errors, then export again; if it still fails, report it to the skill owner.")
        smoke: bool | None = None
        if args.target == "linux":
            ctx.progress(75, "smoke-testing the Linux build")
            out_path.chmod(0o755)
            sm = C.run_proc(ctx, [str(out_path), "--headless", "--audio-driver", "Dummy", "--fixed-fps", "30", "--quit-after", "60"],
                            timeout_s=60, env=C.godot_env(), cwd=build)
            sm_errs = [e.message for e in C.errors_of(C.parse_log(sm.stderr))]
            smoke = sm.returncode == 0 and not sm.timed_out and not sm_errs
            if not smoke:
                errs += sm_errs[:10]
                uncertain.append("The exported Linux game reported errors or failed in its 2-second headless smoke test.")
        else:
            uncertain.append("The web build was checked for its files only; it was not played in a browser here.")
        ctx.progress(90, "packing the build")
        zip_name = f"game_{args.target}.zip"
        zp = ctx.output_path(zip_name)
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in files:
                info = zipfile.ZipInfo(p.name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o755 if p == out_path and args.target == "linux" else 0o644) << 16
                zf.writestr(info, p.read_bytes())
        data = ExportOut(target=args.target, files=[BuiltFile(name=p.name, bytes=p.stat().st_size) for p in files],
                         smoke_ok=smoke, errors=errs[:20])
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
        shutil.rmtree(build, ignore_errors=True)
    desc = ("Web build: unzip and serve the folder from any static web host (open index.html over http, not file://)."
            if args.target == "web" else "Linux build: unzip, keep the .pck beside the executable, and run the .x86_64 file.")
    status = "partial" if smoke is False else "ok"
    total = sum(f.bytes for f in data.files)
    return ToolResult(data=data, outputs=[OutputFile(zp, desc)], status=status, uncertain=uncertain,
                      summary=f"Exported a {args.target} build: {len(data.files)} files, {total / 1e6:.1f} MB"
                              + ("" if smoke is None else ("; smoke test passed" if smoke else "; smoke test failed")),
                      next_step=("Give the user the download link for the build zip and tell them: " + desc) if status == "ok" else
                      "Run run_game to see the runtime errors, fix them, and export again.")


def _slug(name: str) -> str:
    import re

    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return s or "game"
