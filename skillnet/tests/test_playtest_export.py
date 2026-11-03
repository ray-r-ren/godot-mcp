"""playtest_game (simulated input + live-state assertions) and export_game on real Godot 4.4."""
import zipfile

from conftest import output_path
from tools import check_tools as K
from tools import run_tools as R


def test_playtest_move_right_collects_coin(session, red_project_zip):
    steps = [
        {"eval": "$Player.position.x", "label": "start x"},
        {"eval": "score"},
        {"action": "move_right", "hold_ms": 1000},
        {"assert": "$Player.position.x > 250", "label": "player moved right"},
        {"assert": "score == 10", "label": "coin collected"},
        {"assert": "not has_node('Coin')", "label": "coin removed"},
        {"screenshot": "after_move"},
    ]
    r = session.call(R.playtest_game, {"project": str(red_project_zip), "steps": steps})
    assert r["status"] == "ok", r
    d = r["data"]
    assert d["steps_run"] == 7 and d["assertions_passed"] == 3 and d["assertions_failed"] == 0 and d["step_errors"] == 0
    res = d["results"]
    assert res[0]["value"] == 100 and res[1]["value"] == 0
    assert res[3]["passed"] is True and res[3]["label"] == "player moved right"
    assert d["runtime_errors"] == [] and d["crashed"] is False
    assert d["screenshots"][0]["name"] == "after_move"
    assert output_path(r, "after_move.png").stat().st_size > 0
    # Project files are untouched: no helper autoload left behind.
    assert "_Skillnet" not in (session.project / "project.godot").read_text()


def test_playtest_false_assert_unknown_action_and_bad_node(top_down):
    steps = [
        {"assert": "score == 99", "label": "deliberately false"},
        {"action": "fly"},
        {"eval": "$Nope.position"},
        {"key": "NotAKey"},
        {"eval": "score = 5"},
        {"wait_until": "score >= 3", "timeout_ms": 300},
        {"eval": "Input.is_action_pressed('move_right')"},
    ]
    r = top_down.call(R.playtest_game, {"steps": steps})
    d = r["data"]
    res = d["results"]
    assert d["assertions_failed"] == 1 and res[0]["passed"] is False and res[0]["value"] is False
    assert res[1]["ok"] is False and "unknown input action 'fly'" in res[1]["error"] and "move_right" in res[1]["error"]
    assert res[2]["ok"] is False
    assert any("Nope" in e["message"] and e["step"] == 2 for e in d["runtime_errors"])
    assert res[3]["ok"] is False and "unknown key name" in res[3]["error"]
    assert res[4]["ok"] is False and "parse error" in res[4]["error"]
    assert res[5]["ok"] is False and "still false" in res[5]["error"]
    assert res[6]["ok"] is True and res[6]["value"] is False
    assert d["step_errors"] == 5
    assert "fix the game" in r["next_step"]


def test_playtest_platformer_jump(session):
    from tools import project_tools as P
    session.call(P.create_game_project, {"name": "Jumper", "starter": "platformer"})
    steps = [
        {"wait_until": "$Player.is_on_floor()", "timeout_ms": 2000},
        {"eval": "$Player.position.y"},
        {"action": "jump", "hold_ms": 100},
        {"wait_ms": 200},
        {"assert": "not $Player.is_on_floor()", "label": "in the air"},
        {"wait_until": "$Player.is_on_floor()", "timeout_ms": 3000},
    ]
    r = session.call(R.playtest_game, {"steps": steps})
    d = r["data"]
    assert d["assertions_passed"] == 1 and d["step_errors"] == 0, d["results"]
    assert 560 < d["results"][1]["value"] < 590


def test_playtest_invalid_screenshot_name(top_down):
    r = top_down.call(R.playtest_game, {"steps": [{"screenshot": "../evil"}]})
    assert r["status"] == "error" and r["error"]["code"] == "invalid_step"
    assert "Rename" in r["next_step"]


def test_playtest_step_with_two_kinds_is_rejected(top_down):
    r = top_down.call(R.playtest_game, {"steps": [{"action": "jump", "eval": "score"}]})
    assert r["status"] == "error"


def test_export_web(session, red_project_zip):
    r = session.call(K.export_game, {"project": str(red_project_zip), "target": "web"})
    assert r["status"] == "ok", r
    names = {f["name"] for f in r["data"]["files"]}
    assert {"index.html", "index.js", "index.wasm", "index.pck"} <= names
    zf = zipfile.ZipFile(output_path(r, "game_web.zip"))
    assert {"index.html", "index.wasm", "index.pck"} <= set(zf.namelist())
    assert b"<canvas" in zf.read("index.html")
    assert any("browser" in u for u in r["uncertain"])
    assert "http" in r["next_step"]


def test_export_linux_smoke(top_down):
    r = top_down.call(K.export_game, {"target": "linux"})
    assert r["status"] == "ok", r
    d = r["data"]
    assert d["smoke_ok"] is True and d["errors"] == []
    names = {f["name"] for f in d["files"]}
    assert "coin_dash.x86_64" in names and "coin_dash.pck" in names
    zf = zipfile.ZipFile(output_path(r, "game_linux.zip"))
    info = zf.getinfo("coin_dash.x86_64")
    assert (info.external_attr >> 16) & 0o111  # executable bit kept
    with zf.open("coin_dash.x86_64") as fh:
        assert fh.read(4) == b"\x7fELF"


def test_export_without_project_errors(session):
    r = session.call(K.export_game, {"target": "web"})
    assert r["status"] == "error" and r["error"]["code"] == "no_project"
