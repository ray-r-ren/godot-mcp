"""Run the game in a virtual display, and play-test it with scripted input."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, model_validator

from skillnet_sdk import OutputFile, ToolContext, ToolError, ToolInput, ToolOutput, ToolResult, tool

from . import common as C
from .project_tools import STATE_V, ProjectZip

FPS = C.FIXED_FPS


class RuntimeErr(ToolOutput):
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    function: Optional[str] = None
    step: Optional[int] = None


class ShotInfo(ToolOutput):
    t: Optional[float] = None
    name: Optional[str] = None
    file: str
    mean_color: str
    mean_rgb: list[int]
    dominant_color: str = Field(description="Most common exact pixel colour, usually the background")
    dominant_share: float = Field(description="Fraction of the frame that has the dominant colour")
    blank: bool


def _prepare(ctx: ToolContext, project: Path, scene: Optional[str]) -> tuple[Path, str]:
    """Import, validate the scene to run, and make a throwaway copy with our helper folder."""
    C.godot_import(ctx, project)
    target = scene
    if target:
        rel = C.res_to_rel(target)
        if not (project / rel).is_file() or not rel.endswith((".tscn", ".scn")):
            raise ToolError("scene_not_found", f"{target} is not a scene in the project.",
                            "Call inspect_project to list the scenes and pass one of their res:// paths.")
        target = C.rel_to_res(rel)
    else:
        target = C.main_scene_of(project)
        if not target or not target.startswith("res://") or not (project / target[6:]).is_file():
            raise ToolError("no_main_scene", "The project has no valid main scene to run.",
                            "Pass `scene` with a res:// scene path, or set the main scene with edit_scenes (op set_main_scene).")
    work = C.work_copy(project)
    (work / "_skillnet").mkdir(exist_ok=True)
    if scene:
        C.set_main_scene_text(work, target)
    return work, target


def _godot_run_args(work: Path, width: Optional[int], height: Optional[int]) -> list[str]:
    a = [C.GODOT, "--path", str(work), "--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3",
         "--audio-driver", "Dummy", "--fixed-fps", str(FPS), "--disable-vsync", "--windowed"]
    if width and height:
        a += ["--resolution", f"{width}x{height}"]
    return a


def _viewport_size(project: Path) -> tuple[int, int]:
    try:
        d = C.read_project_godot(project).get("display", {})
        return int(d.get("window/size/viewport_width", 1152)), int(d.get("window/size/viewport_height", 648))
    except (OSError, ValueError):
        return 1152, 648


# =============================================================================== run_game

class RunIn(ToolInput):
    project: Optional[ProjectZip] = Field(default=None, description="A Godot 4 project zip to run (omit when passing a state_id).")
    scene: Optional[str] = Field(default=None, description="res:// path of a scene to run instead of the main scene (e.g. to render one level or a UI screen).")
    seconds: float = Field(default=5.0, ge=0.2, le=60, description="Game time to run, 0.2-60 s. Use 0.2 for a still render of a scene.")
    screenshot_at: Optional[list[float]] = Field(default=None, max_length=12, description="Game-time moments (seconds) for screenshots, up to 12. Default: one at the end.")
    record_video: bool = Field(default=False, description="Also record an MP4 of the whole run (30 fps).")
    width: Optional[int] = Field(default=None, ge=160, le=1920, description="Window width in pixels (default: the project's viewport width).")
    height: Optional[int] = Field(default=None, ge=120, le=1080, description="Window height in pixels (default: the project's viewport height).")


class RunOut(ToolOutput):
    scene: str
    started: bool
    crashed: bool
    finished: bool
    exit_code: Optional[int]
    frames_rendered: int
    runtime_errors: list[RuntimeErr]
    warnings: list[str]
    screenshots: list[ShotInfo]
    log_tail: str


@tool(kind="analyze", title="Run the game and capture what it shows", timeout_s=420, long_running=True, state_version=STATE_V,
      examples=[{"arguments": {"seconds": 4, "screenshot_at": [1, 4]}}])
def run_game(args: RunIn, ctx: ToolContext) -> ToolResult[RunOut]:
    """Use to see the game working (or crashing) with no input: runs the main scene, or a chosen scene, in a virtual display with the OpenGL software renderer at a fixed 30 fps for a set game time. Returns whether it crashed, runtime errors with file and line, screenshots at chosen moments (each with its mean colour, its dominant (background) colour and a blank-frame flag), a contact sheet, the console log and optionally an MP4. seconds=0.2 gives a still render of one scene. Use playtest_game when the game needs input."""
    project = C.load_project(ctx, args.project)
    assert project is not None
    times = sorted({round(min(max(t, 0.0), args.seconds), 3) for t in (args.screenshot_at or [args.seconds])})
    work, target = _prepare(ctx, project, args.scene)
    tmp = Path(tempfile.mkdtemp(prefix="skn-out-"))
    try:
        shutil.copy(C.GD_DIR / "run_capture.gd", work / "_skillnet" / "run_capture.gd")
        C.add_autoload_text(work, "_SkillnetRun", "res://_skillnet/run_capture.gd")
        cfg = {"fps": FPS, "seconds": args.seconds, "screenshot_at": times, "out_dir": str(tmp), "info_path": str(tmp / "info.json")}
        (tmp / "cfg.json").write_text(json.dumps(cfg))
        vw, vh = _viewport_size(project)
        w, h = args.width or vw, args.height or vh
        cmd = _godot_run_args(work, args.width or None, args.height or None)
        movie = tmp / "movie.avi"
        if args.record_video:
            cmd += ["--write-movie", str(movie)]
        cmd += ["--", f"--skillnet-run={tmp / 'cfg.json'}"]
        ctx.progress(15, f"running {target} for {args.seconds:g}s of game time")
        budget = min(30 + args.seconds * (10 if args.record_video else 5), 330)
        with C.virtual_display(max(w, 640) + 64, max(h, 480) + 64) as disp:
            res = C.run_proc(ctx, cmd, timeout_s=budget, env=C.godot_env(disp))
        ctx.progress(75, "collecting screenshots and errors")
        info = json.loads((tmp / "info.json").read_text()) if (tmp / "info.json").exists() else None
        info_partial: dict = {"frames": 0, "shots": []}
        if info is None:  # stopped early: recover the frame count and any screenshots already taken
            beats = re.findall(r"\[SKN-RUN\] frame (\d+)", res.stdout)
            got = []
            for f in sorted(tmp.glob("shot_*.png")):
                i = int(f.stem.split("_")[1])
                got.append({"index": i, "frame": None, "path": str(f)})
            info_partial = {"frames": int(beats[-1]) if beats else 0, "shots": got}
        started = "[SKN-RUN] started" in res.stdout
        finished = info is not None
        crashed = not finished and not res.timed_out and (res.returncode not in (0, None) or not started)
        quit_early = not finished and not res.timed_out and res.returncode == 0 and started
        entries = C.parse_log(res.stderr + "\n" + res.stdout)
        errs = [RuntimeErr(**e.as_dict()) for e in C.errors_of(entries)][:30]
        warns = [e.message[:200] for e in C.warnings_of(entries)][:10]
        shots: list[ShotInfo] = []
        sheet_items = []
        outputs: list[OutputFile] = []
        for s in (info or info_partial).get("shots", []):
            src = Path(s["path"])
            if not src.exists():
                continue
            t = times[s["index"]] if s["index"] < len(times) else (s["frame"] or 0) / FPS
            name = f"screenshot_t{t:g}s.png"
            dst = ctx.output_path(name)
            shutil.copy(src, dst)
            rgb, hexc, blank, dom, share = C.analyze_png(dst)
            shots.append(ShotInfo(t=t, file=name, mean_color=hexc, mean_rgb=rgb, dominant_color=dom,
                                  dominant_share=share, blank=blank))
            sheet_items.append((f"t={t:g}s", dst))
            outputs.append(OutputFile(dst, f"Screenshot at {t:g}s of game time"))
        if len(sheet_items) > 1:
            sheet = C.contact_sheet(sheet_items, ctx.output_path("contact_sheet.png"))
            if sheet:
                outputs.append(OutputFile(sheet, "All screenshots on one sheet"))
        log_text = C.clean_log(res.stdout + "\n" + res.stderr)
        lp = ctx.output_path("run_log.txt")
        lp.write_text(log_text[-400_000:])
        outputs.append(OutputFile(lp, "Console output of the run"))
        uncertain: list[str] = []
        if args.record_video:
            if movie.exists():
                mp4 = ctx.output_path("gameplay.mp4")
                conv = C.run_proc(ctx, ["ffmpeg", "-y", "-loglevel", "error", "-i", str(movie), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                        "-preset", "veryfast", "-crf", "24", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", str(mp4)], timeout_s=180)
                if conv.returncode == 0 and mp4.exists():
                    outputs.append(OutputFile(mp4, f"Video of the run ({FPS} fps)"))
                else:
                    uncertain.append("The video could not be converted to MP4.")
            else:
                uncertain.append("No video was recorded (the game stopped before the first frame).")
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    if C.renderer_of(project) != "gl_compatibility":
        uncertain.append(f"The project uses the {C.renderer_of(project)} renderer; it was run with the Compatibility renderer, so lighting and effects may look different.")
    if any(s.blank for s in shots):
        uncertain.append("Some screenshots are a single flat colour: the scene may be empty, the camera may be missing, or nodes may sit outside the view.")
    if res.timed_out:
        uncertain.append(f"The run did not finish within {budget:.0f}s of real time and was stopped (the game may be stuck in a loop or rendering very slowly).")
    if quit_early:
        uncertain.append("The game quit by itself before the requested time.")
    tail = "\n".join(log_text.splitlines()[-15:])[-1500:]
    data = RunOut(scene=target, started=started, crashed=crashed, finished=finished, exit_code=res.returncode,
                  frames_rendered=(info or info_partial).get("frames", 0), runtime_errors=errs, warnings=warns, screenshots=shots, log_tail=tail)
    ctx.mark_untrusted("game output")
    if res.timed_out and not data.frames_rendered:
        summary = f"The game hung: no frame was rendered within {budget:.0f}s of real time; {len(errs)} error(s)"
        nxt = ("Look for an endless loop in _init(), _ready() or the first _process() (a while loop that never ends), "
               "fix it with write_game_files, then run again.")
        status = "partial"
    elif crashed:
        summary = f"The game crashed or failed to start (exit {res.returncode}); {len(errs)} error(s)"
        nxt = "Read runtime_errors and log_tail, fix the cause with write_game_files, run check_project, then run_game again."
        status = "ok"
    elif errs:
        summary = f"Ran {target} for {data.frames_rendered / FPS:.1f}s with {len(errs)} runtime error(s)"
        nxt = "Fix each runtime error (file and line) with write_game_files, then run again."
        status = "ok"
    else:
        summary = f"Ran {target} for {data.frames_rendered / FPS:.1f}s with no errors; {len(shots)} screenshot(s)"
        nxt = "Look at the screenshots; then check gameplay with playtest_game."
        status = "partial" if (res.timed_out or quit_early) else "ok"
    return ToolResult(data=data, outputs=outputs, summary=summary, uncertain=uncertain, status=status, next_step=nxt)


# =============================================================================== playtest

class Step(ToolInput):
    action: Optional[str] = Field(default=None, description="Press an input action (e.g. move_right, jump) for hold_ms.")
    key: Optional[str] = Field(default=None, description="Press a keyboard key by name (A, Space, Enter, Escape, Left, Up, Shift...) for hold_ms.")
    click: Optional[list[float]] = Field(default=None, min_length=2, max_length=2, description="Click the mouse at [x, y] window pixels.")
    button: Literal["left", "right", "middle"] = Field(default="left", description="Mouse button for click.")
    hold_ms: int = Field(default=100, ge=0, le=30000, description="How long action/key/click is held, in game milliseconds.")
    wait_ms: Optional[int] = Field(default=None, ge=0, le=60000, description="Let the game run this many game milliseconds with no input.")
    screenshot: Optional[str] = Field(default=None, max_length=40, description="Take a screenshot with this name (letters, digits, - and _).")
    eval: Optional[str] = Field(default=None, max_length=2000, description="GDScript expression to read live state, e.g. $Player.position or score; evaluated on the current scene root.")
    assert_: Optional[str] = Field(default=None, alias="assert", max_length=2000, description="GDScript expression that must be true, e.g. $Player.position.x > 600 or score >= 1.")
    wait_until: Optional[str] = Field(default=None, max_length=2000, description="Wait until this expression is true (up to timeout_ms), e.g. score >= 1.")
    timeout_ms: int = Field(default=5000, ge=100, le=60000, description="Limit for wait_until, in game milliseconds.")
    label: Optional[str] = Field(default=None, max_length=120, description="A note shown with this step's result, e.g. 'player moved right'.")

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def _one_kind(self) -> "Step":
        kinds = [k for k in ("action", "key", "click", "wait_ms", "screenshot", "eval", "assert_", "wait_until") if getattr(self, k) is not None]
        if len(kinds) != 1:
            raise ValueError("each step needs exactly one of: action, key, click, wait_ms, screenshot, eval, assert, wait_until")
        return self


class PlayIn(ToolInput):
    project: Optional[ProjectZip] = Field(default=None, description="A Godot 4 project zip to play-test (omit when passing a state_id).")
    steps: list[Step] = Field(min_length=1, max_length=200, description="The play-test script, run in order (up to 200 steps).")
    scene: Optional[str] = Field(default=None, description="res:// scene to start in instead of the main scene.")
    timeout_s: int = Field(default=120, ge=10, le=600, description="Real-time limit for the whole play-test, in seconds.")
    width: Optional[int] = Field(default=None, ge=160, le=1920, description="Window width (default: the project's viewport width).")
    height: Optional[int] = Field(default=None, ge=120, le=1080, description="Window height (default: the project's viewport height).")


class StepResult(ToolOutput):
    index: int
    step: str
    ok: bool
    label: Optional[str] = None
    value: Optional[object] = None
    error: Optional[str] = None
    passed: Optional[bool] = None


class PlayOut(ToolOutput):
    steps_run: int
    steps_total: int
    assertions_passed: int
    assertions_failed: int
    step_errors: int
    results: list[StepResult]
    runtime_errors: list[RuntimeErr]
    crashed: bool
    screenshots: list[ShotInfo]


_DOLLAR = re.compile(r'\$(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*))')
_UNIQUE = re.compile(r'(?<![\w"])%([A-Za-z_][A-Za-z0-9_]*)')


def to_expression(src: str) -> str:
    """GDScript's $Node / %Unique shorthands aren't valid in Expression: turn them into get_node()."""
    out = _DOLLAR.sub(lambda m: f'get_node("{m.group(1) or m.group(2)}")', src)
    return _UNIQUE.sub(lambda m: f'get_node("%{m.group(1)}")', out)


def _frames(ms: int) -> int:
    return max(0, round(ms * FPS / 1000))


def _describe(s: Step) -> str:
    if s.action is not None:
        return f"action {s.action} {s.hold_ms}ms"
    if s.key is not None:
        return f"key {s.key} {s.hold_ms}ms"
    if s.click is not None:
        return f"click {s.button} at {int(s.click[0])},{int(s.click[1])}"
    if s.wait_ms is not None:
        return f"wait {s.wait_ms}ms"
    if s.screenshot is not None:
        return f"screenshot {s.screenshot}"
    if s.eval is not None:
        return f"eval {s.eval}"[:200]
    if s.assert_ is not None:
        return f"assert {s.assert_}"[:200]
    return f"wait_until {s.wait_until}"[:200]


def _normalize(i: int, s: Step) -> dict:
    hold = max(1, _frames(s.hold_ms))
    if s.action is not None:
        return {"kind": "action", "action": s.action, "hold_frames": hold}
    if s.key is not None:
        return {"kind": "key", "key": s.key, "hold_frames": hold}
    if s.click is not None:
        return {"kind": "click", "x": s.click[0], "y": s.click[1], "button": s.button, "hold_frames": max(1, _frames(min(s.hold_ms, 100)))}
    if s.wait_ms is not None:
        return {"kind": "wait", "frames": _frames(s.wait_ms)}
    if s.screenshot is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", s.screenshot):
            raise ToolError("invalid_step", f"Step {i}: screenshot name '{s.screenshot}' may use only letters, digits, - and _.",
                            f"Rename the screenshot in step {i}, e.g. 'after_jump'.")
        return {"kind": "screenshot", "name": s.screenshot}
    if s.eval is not None:
        return {"kind": "eval", "expr": to_expression(s.eval)}
    if s.assert_ is not None:
        return {"kind": "assert", "expr": to_expression(s.assert_)}
    return {"kind": "wait_until", "expr": to_expression(s.wait_until or ""), "timeout_frames": max(1, _frames(s.timeout_ms))}


@tool(kind="check", title="Play-test the game with simulated input", timeout_s=660, long_running=True, state_version=STATE_V,
      examples=[{"arguments": {"steps": [{"eval": "$Player.position"}, {"action": "move_right", "hold_ms": 800},
                                         {"assert": "$Player.position.x > 600", "label": "player moved right"}, {"screenshot": "after_move"}]}}])
def playtest_game(args: PlayIn, ctx: ToolContext) -> ToolResult[PlayOut]:
    """Use to check that gameplay works: runs the game in a virtual display at a fixed 30 fps and plays a scripted sequence in one call, with steps {action:'move_right', hold_ms}, {key:'Space'}, {click:[x,y]}, {wait_ms}, {screenshot:'name'}, {eval:'$Player.position'} to read live state, {assert:'score >= 1', label} and {wait_until:'expr', timeout_ms}. Returns each step's result, assertion pass/fail with values, screenshots and runtime errors. Project files stay unchanged. Call inspect_project first to find action names and node paths."""
    project = C.load_project(ctx, args.project)
    assert project is not None
    steps = [_normalize(i, s) for i, s in enumerate(args.steps)]
    names = [s["name"] for s in steps if s["kind"] == "screenshot"]
    if len(names) != len(set(names)):
        raise ToolError("invalid_step", "Two screenshot steps use the same name.", "Give every screenshot step a different name.")
    work, target = _prepare(ctx, project, args.scene)
    tmp = Path(tempfile.mkdtemp(prefix="skn-play-"))
    try:
        shutil.copy(C.GD_DIR / "playtest.gd", work / "_skillnet" / "playtest.gd")
        C.add_autoload_text(work, "_SkillnetPlaytest", "res://_skillnet/playtest.gd")
        results_path = tmp / "results.jsonl"
        (tmp / "cfg.json").write_text(json.dumps({"fps": FPS, "steps": steps, "out_dir": str(tmp), "results_path": str(results_path), "warmup_frames": 3}))
        vw, vh = _viewport_size(project)
        w, h = args.width or vw, args.height or vh
        cmd = _godot_run_args(work, args.width or None, args.height or None) + ["--", f"--skillnet-playtest={tmp / 'cfg.json'}"]
        ctx.progress(15, f"playing {len(steps)} step(s) in {target}")
        with C.virtual_display(max(w, 640) + 64, max(h, 480) + 64) as disp:
            res = C.run_proc(ctx, cmd, timeout_s=args.timeout_s, env=C.godot_env(disp))
        ctx.progress(80, "collecting results")
        lines = []
        if results_path.exists():
            for ln in results_path.read_text().splitlines():
                try:
                    lines.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
        ended = any(d.get("type") == "end" for d in lines)
        by_index = {d["index"]: d for d in lines if "index" in d}
        results: list[StepResult] = []
        shots: list[ShotInfo] = []
        outputs: list[OutputFile] = []
        sheet_items = []
        passed = failed = step_errors = 0
        for i, s in enumerate(args.steps):
            d = by_index.get(i)
            if d is None:
                break
            r = StepResult(index=i, step=_describe(s), ok=bool(d.get("ok")), label=s.label, value=d.get("value"), error=d.get("error"), passed=d.get("passed"))
            if s.assert_ is not None:
                if d.get("passed"):
                    passed += 1
                else:
                    failed += 1
            elif not r.ok:
                step_errors += 1
            if s.screenshot is not None and d.get("file"):
                src = tmp / d["file"]
                if src.exists():
                    name = f"{s.screenshot}.png"
                    dst = ctx.output_path(name)
                    shutil.copy(src, dst)
                    rgb, hexc, blank, dom, share = C.analyze_png(dst)
                    shots.append(ShotInfo(name=s.screenshot, file=name, mean_color=hexc, mean_rgb=rgb,
                                          dominant_color=dom, dominant_share=share, blank=blank))
                    sheet_items.append((s.screenshot, dst))
                    outputs.append(OutputFile(dst, f"Screenshot '{s.screenshot}' (after step {i})"))
            results.append(r)
        if len(sheet_items) > 1:
            sheet = C.contact_sheet(sheet_items, ctx.output_path("contact_sheet.png"))
            if sheet:
                outputs.append(OutputFile(sheet, "All play-test screenshots on one sheet"))
        entries = C.parse_log(res.stderr)
        errs = [RuntimeErr(**e.as_dict()) for e in C.errors_of(entries)][:30]
        for e in errs:
            if e.step is not None and e.step < 0:
                e.step = None
        log_text = C.clean_log(res.stdout + "\n" + res.stderr)
        lp = ctx.output_path("playtest_log.txt")
        lp.write_text(log_text[-400_000:])
        outputs.append(OutputFile(lp, "Console output of the play-test"))
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    stopped = not ended and not res.timed_out
    quit_by_game = stopped and res.returncode == 0
    crashed = stopped and not quit_by_game
    uncertain: list[str] = []
    if res.timed_out:
        uncertain.append(f"The play-test hit its {args.timeout_s}s real-time limit after {len(results)} of {len(steps)} steps.")
    elif quit_by_game:
        uncertain.append(f"The game quit by itself (exit 0) after {len(results)} of {len(steps)} steps; later steps did not run.")
    elif crashed:
        uncertain.append(f"The game crashed (exit {res.returncode}) after {len(results)} of {len(steps)} steps.")
    if any(s.blank for s in shots):
        uncertain.append("Some screenshots are a single flat colour (empty view, missing camera, or nodes outside the view).")
    if C.renderer_of(project) != "gl_compatibility":
        uncertain.append("The project was run with the Compatibility renderer instead of its own.")
    data = PlayOut(steps_run=len(results), steps_total=len(steps), assertions_passed=passed, assertions_failed=failed,
                   step_errors=step_errors, results=results, runtime_errors=errs, crashed=crashed, screenshots=shots)
    ctx.mark_untrusted("game output")
    status = "partial" if (res.timed_out or stopped) else "ok"
    n_assert = passed + failed
    summary = (f"Ran {len(results)}/{len(steps)} steps in {target}: {passed}/{n_assert} assertions passed"
               + (f", {step_errors} step error(s)" if step_errors else "") + (f", {len(errs)} runtime error(s)" if errs else "")
               + ("; the game crashed" if crashed else "") + ("; the game quit by itself" if quit_by_game else "")
               + ("; timed out" if res.timed_out else ""))
    if failed or step_errors or errs or stopped:
        nxt = "Look at failing steps (value/error) and runtime_errors, fix the game with write_game_files or edit_scenes, then play-test again."
    else:
        nxt = "Show the user the assertion results and screenshots; export with export_game if they want a build."
    return ToolResult(data=data, outputs=outputs, summary=summary, uncertain=uncertain, status=status, next_step=nxt)
