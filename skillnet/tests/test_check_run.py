"""check_project and run_game on real Godot 4.4 in a virtual display (software OpenGL)."""
import json
import zipfile
import subprocess

from PIL import Image

from conftest import output_path
from tools import check_tools as K
from tools import project_tools as P
from tools import run_tools as R


def test_check_clean_project_is_ready(session, red_project_zip):
    r = session.call(K.check_project, {"project": str(red_project_zip)})
    assert r["status"] == "ok", r
    d = r["data"]
    assert d["verdict"] == "ready" and d["errors"] == []
    assert d["scripts_checked"] == 3 and d["scenes_checked"] == 1
    assert d["main_scene"] == "res://main.tscn"
    report = json.loads(output_path(r, "check_report.json").read_text())
    assert report["verdict"] == "ready"


def test_check_broken_project_lists_file_and_line(session, broken_project_zip):
    r = session.call(K.check_project, {"project": str(broken_project_zip)})
    d = r["data"]
    assert d["verdict"] == "has_errors"
    parse = [e for e in d["errors"] if e.get("file") == "res://main.gd" and e.get("line") == 7]
    assert parse and "Expected \":\"" in parse[0]["message"]
    assert any("missing_enemy.gd" in e["message"] for e in d["errors"])
    assert len(d["errors"]) == 2, d["errors"]  # root causes only: no engine echoes of the same two problems
    assert "write_game_files" in r["next_step"]


def test_check_flags_godot3_node_type_with_rename_hint(session):
    session.call(P.create_game_project, {"name": "Old Nodes", "starter": "blank_2d"})
    session.call(P.edit_scenes, {"operations": [
        {"op": "add_node", "scene": "res://scenes/main.tscn", "parent": ".", "type": "Node2D", "name": "Hero"}]})
    tscn = session.project / "scenes" / "main.tscn"
    tscn.write_text(tscn.read_text().replace('name="Hero" type="Node2D"', 'name="Hero" type="KinematicBody2D"'))
    r = session.call(K.check_project, {})
    d = r["data"]
    assert d["verdict"] == "has_errors"
    hit = [e for e in d["errors"] if "KinematicBody2D" in e["message"]]
    assert hit and hit[0].get("file") == "res://scenes/main.tscn" and "CharacterBody2D" in hit[0]["message"], d["errors"]


def test_check_finds_connection_to_missing_method(session):
    session.call(P.create_game_project, {"name": "Conn", "starter": "blank_2d"})
    session.call(P.edit_scenes, {"operations": [
        {"op": "add_node", "scene": "res://scenes/main.tscn", "parent": ".", "type": "Timer", "name": "T"},
        {"op": "connect_signal", "scene": "res://scenes/main.tscn", "node": "T", "signal": "timeout", "method": "_on_t"}]})
    r = session.call(K.check_project, {})
    assert r["data"]["verdict"] == "has_errors"
    assert any("_on_t" in e["message"] and e.get("file") == "res://scenes/main.tscn" for e in r["data"]["errors"])


def test_check_without_project_errors(session):
    r = session.call(K.check_project, {})
    assert r["status"] == "error" and r["error"]["code"] == "no_project"


def test_run_red_background_screenshot_and_video(session, red_project_zip):
    r = session.call(R.run_game, {"project": str(red_project_zip), "seconds": 2, "screenshot_at": [0.5, 2], "record_video": True})
    assert r["status"] == "ok", r
    d = r["data"]
    assert d["started"] and d["finished"] and not d["crashed"] and d["runtime_errors"] == []
    assert d["frames_rendered"] == 60
    assert [s["t"] for s in d["screenshots"]] == [0.5, 2.0]
    shot = d["screenshots"][0]
    red, green, blue = shot["mean_rgb"]
    # The background is Color(0.9, 0.1, 0.1) ~ (230, 25, 25) and fills the window (player and coin have no visuals).
    assert red > 200 and green < 60 and blue < 60, shot
    # The dominant exact colour is the background itself: Color(0.9, 0.1, 0.1) -> #e61a1a.
    dom = shot["dominant_color"]
    assert shot["dominant_share"] > 0.9
    assert max(abs(int(dom[i:i + 2], 16) - v) for i, v in ((1, 230), (3, 26), (5, 26))) <= 3, dom
    img = Image.open(output_path(r, "screenshot_t0.5s.png"))
    assert img.size == (640, 360)
    px = img.convert("RGB").getpixel((600, 20))
    assert abs(px[0] - 230) <= 2 and abs(px[1] - 25) <= 2 and abs(px[2] - 25) <= 2, px
    assert output_path(r, "contact_sheet.png").exists()
    mp4 = output_path(r, "gameplay.mp4")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,nb_frames",
                            "-of", "json", str(mp4)], capture_output=True, text=True, check=True)
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["codec_name"] == "h264" and stream["width"] == 640 and stream["height"] == 360
    assert int(stream["nb_frames"]) >= 55


def test_run_reports_runtime_error_with_file_and_line(session, crash_project_zip):
    r = session.call(R.run_game, {"project": str(crash_project_zip), "seconds": 1.5})
    d = r["data"]
    assert d["started"] and not d["crashed"]
    errs = d["runtime_errors"]
    assert len(errs) == 1  # the same error every frame is reported once
    assert errs[0]["file"] == "res://main.gd" and errs[0]["line"] == 10 and "Nil" in errs[0]["message"]
    assert "runtime error" in r["summary"]
    # A full-screen single colour is flagged as a flat frame, honestly.
    assert d["screenshots"][0]["blank"] is True and d["screenshots"][0]["mean_color"] == "#0000ff"
    assert any("flat colour" in u for u in r["uncertain"])


def test_run_chosen_scene_still_render(top_down):
    r = top_down.call(R.run_game, {"scene": "res://scenes/coin.tscn", "seconds": 0.2})
    assert r["status"] == "ok", r
    assert r["data"]["scene"] == "res://scenes/coin.tscn" and r["data"]["frames_rendered"] == 6


def test_run_unknown_scene_errors(top_down):
    r = top_down.call(R.run_game, {"scene": "res://scenes/nope.tscn"})
    assert r["status"] == "error" and r["error"]["code"] == "scene_not_found"
    assert "inspect_project" in r["next_step"]


def test_signal_to_missing_method_then_write_it_is_ready(session):
    session.call(P.create_game_project, {"name": "Countdown", "starter": "platformer"})
    e = session.call(P.edit_scenes, {"operations": [
        {"op": "add_node", "scene": "res://scenes/main.tscn", "parent": ".", "type": "Timer", "name": "Countdown",
         "properties": {"wait_time": 1, "autostart": True}},
        {"op": "connect_signal", "scene": "res://scenes/main.tscn", "node": "Countdown", "signal": "timeout",
         "target": ".", "method": "_on_countdown_timeout"}]})
    assert e["data"]["applied"] == 2
    r = session.call(K.check_project, {})
    assert r["data"]["verdict"] == "has_errors"
    assert any("_on_countdown_timeout" in x["message"] for x in r["data"]["errors"])
    gd = (session.project / "scripts/main.gd").read_text()
    gd += "\n\nvar time_left := 60\n\n\nfunc _on_countdown_timeout() -> void:\n\ttime_left -= 1\n"
    w = session.call(P.write_game_files, {"files": [{"path": "res://scripts/main.gd", "content": gd}]})
    assert w["data"]["ok"] is True
    r = session.call(K.check_project, {})
    assert r["data"]["verdict"] == "ready" and r["data"]["errors"] == []


def test_check_bad_main_scene_then_set_it(session, red_project_zip, tmp_path):
    import zipfile as zf
    bad = tmp_path / "bad_main.zip"
    with zf.ZipFile(red_project_zip) as src, zf.ZipFile(bad, "w") as dst:
        for n in src.namelist():
            data = src.read(n)
            if n.endswith("project.godot"):
                data = data.replace(b"res://main.tscn", b"res://nowhere.tscn")
            dst.writestr(n, data)
    r = session.call(K.check_project, {"project": str(bad)})
    d = r["data"]
    assert d["verdict"] == "has_errors" and d["main_scene"] == "res://nowhere.tscn"
    assert len(d["errors"]) == 1  # no duplicate engine lines for the same missing file
    assert d["errors"][0]["file"] == "res://project.godot" and "does not exist" in d["errors"][0]["message"]
    assert "set_main_scene" in r["next_step"] and "res://main.tscn" in r["next_step"]
    # Continue on the state the check opened: fix and re-check.
    f = session.call(P.edit_scenes, {"operations": [{"op": "set_main_scene", "scene": "res://main.tscn"}]})
    assert f["status"] == "ok", f
    r = session.call(K.check_project, {})
    assert r["data"]["verdict"] == "ready" and r["data"]["main_scene"] == "res://main.tscn"


def test_check_uploaded_broken_zip_fix_loop(session, broken_project_zip):
    r = session.call(K.check_project, {"project": str(broken_project_zip)})
    assert r["data"]["verdict"] == "has_errors"
    fixed_gd = "extends Node2D\n\nvar lives := 3\n\n\nfunc _ready() -> void:\n\tif lives > 0:\n\t\tprint(\"alive\")\n"
    w = session.call(P.write_game_files, {"files": [{"path": "res://main.gd", "content": fixed_gd}]})
    assert w["data"]["ok"] is True
    r = session.call(K.check_project, {})
    left = r["data"]["errors"]
    assert r["data"]["verdict"] == "has_errors" and all(e["file"] in ("res://main.tscn", "res://missing_enemy.gd") for e in left), left
    assert not any(e["file"] == "res://main.gd" for e in left)
    e = session.call(P.edit_scenes, {"operations": [{"op": "remove_node", "scene": "res://main.tscn", "node": "Enemy"}]})
    assert e["status"] == "ok", e
    r = session.call(K.check_project, {})
    assert r["data"]["verdict"] == "ready", r["data"]["errors"]
    names = zipfile.ZipFile(output_path(w, "project.zip")).namelist()
    assert "main.gd" in names or any(n.endswith("/main.gd") for n in names)


def test_check_refuses_godot3_zip(session, godot3_zip):
    r = session.call(K.check_project, {"project": str(godot3_zip)})
    assert r["status"] == "error" and r["error"]["code"] == "godot3_project"
    assert "converter" in r["next_step"] and "create_game_project" in r["next_step"]
