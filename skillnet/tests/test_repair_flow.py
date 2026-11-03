"""Repairing uploaded Godot 4 projects with Godot 3 leftovers: values survive scene edits, and the final check
lists every problem that was fixed, named precisely."""
import re

from conftest import G3_COIN_GD, VAULT_MAIN_GD
from tools import check_tools as K
from tools import project_tools as P
from tools import run_tools as R


def test_edit_scene_keeps_values_of_nodes_with_broken_scripts(session, g3_coins_zip):
    c = session.call(K.check_project, {"project": str(g3_coins_zip)})
    errs = c["data"]["errors"]
    hint = [e for e in errs if e["file"] == "res://coin.gd"]
    assert hint and hint[0]["line"] == 5 and "@export var" in hint[0]["message"], errs
    e = session.call(P.edit_scenes, {"operations": [{"op": "remove_node", "scene": "res://main.tscn", "node": "Music"}]})
    assert e["status"] == "ok", e
    assert any("BigCoin.value = 3" in u for u in e["uncertain"]), e["uncertain"]
    tscn = (session.project / "main.tscn").read_text()
    big = tscn[tscn.index('[node name="BigCoin"'):]
    assert "value = 3" in big.split("[node", 2)[1] and "Music" not in tscn
    # Now fix the script; the kept value takes effect: touching both coins adds 1 + 3.
    w = session.call(P.write_game_files, {"files": [{"path": "res://coin.gd",
                                                     "content": G3_COIN_GD.replace("export var value = 1", "@export var value := 1")}]})
    assert w["data"]["ok"] is True
    k = session.call(K.check_project, {})
    assert k["data"]["verdict"] == "ready", k["data"]["errors"]
    fixed = " | ".join(k["data"]["fixed_since_first_check"])
    assert "coin.gd:5" in fixed and "music.gd" in fixed
    p = session.call(R.playtest_game, {"steps": [
        {"eval": "$BigCoin.value", "label": "big coin value"},
        {"eval": "$Player.set('position', Vector2(300, 100))"}, {"wait_ms": 200},
        {"eval": "$Player.set('position', Vector2(500, 100))"}, {"wait_ms": 200},
        {"assert": "score == 4", "label": "1 + 3"}]})
    res = p["data"]["results"]
    assert res[0]["value"] == 3 and p["data"]["assertions_passed"] == 1, res


def test_set_properties_to_default_is_not_undone(session, red_project_zip):
    session.call(K.check_project, {"project": str(red_project_zip)})
    e = session.call(P.edit_scenes, {"operations": [
        {"op": "set_properties", "scene": "res://main.tscn", "node": "Player", "properties": {"speed": 200.0}},
        {"op": "set_properties", "scene": "res://main.tscn", "node": "Coin", "properties": {"position": [0, 0]}}]})
    assert e["status"] == "ok" and e["uncertain"] == [], e
    tscn = (session.project / "main.tscn").read_text()
    coin = tscn[tscn.index('[node name="Coin"'):].split("[node", 2)[1]
    assert "position" not in coin  # the default value stays dropped, as asked


def test_vault_repair_names_every_fixed_problem(session, vault_zip):
    c = session.call(K.check_project, {"project": str(vault_zip)})
    errs = c["data"]["errors"]
    assert len(errs) == 3, errs
    conn = [e for e in errs if "_on_timer_timeout" in e["message"]]
    assert conn and conn[0]["file"] == "res://main.tscn" and "Timer.timeout" in conn[0]["message"]
    assert "'Main'" in conn[0]["message"] and "res://main.gd" in conn[0]["message"]
    assert "onready" in c["summary"]
    fixed_gd = VAULT_MAIN_GD.replace("onready", "@onready")
    w = session.call(P.write_game_files, {"files": [{"path": "res://main.gd", "content": fixed_gd},
                                                     {"path": "res://guard.gd", "content": "extends Node2D\n"}]})
    assert w["data"]["ok"] is True
    mid = session.call(K.check_project, {})
    assert mid["data"]["verdict"] == "has_errors" and len(mid["data"]["fixed_since_first_check"]) == 2
    session.call(P.write_game_files, {"files": [{"path": "res://main.gd", "content":
                                                 fixed_gd + "\n\nfunc _on_timer_timeout() -> void:\n\tticks += 1\n"}]})
    r = session.call(K.check_project, {})
    d = r["data"]
    assert d["verdict"] == "ready"
    fixed = " | ".join(d["fixed_since_first_check"])
    assert "main.gd:3" in fixed and "onready" in fixed and "guard.gd" in fixed and "_on_timer_timeout" in fixed
    assert "3 earlier problem(s) fixed" in r["summary"] and "fixed_since_first_check" in r["next_step"]
    # A new upload starts a fresh history.
    again = session.call(K.check_project, {"project": str(vault_zip)})
    assert again["data"]["fixed_since_first_check"] == []


def test_no_missing_method_alarm_when_the_script_only_fails_to_parse(session, vault_zip, tmp_path):
    import zipfile
    z = tmp_path / "v2.zip"
    with zipfile.ZipFile(vault_zip) as src, zipfile.ZipFile(z, "w") as dst:
        for n in src.namelist():
            data = src.read(n)
            if n.endswith("main.gd"):
                data += b"\n\nfunc _on_timer_timeout() -> void:\n\tticks += 1\n"
            dst.writestr(n, data)
        dst.writestr("guard.gd", "extends Node2D\n")
    errs = session.call(K.check_project, {"project": str(z)})["data"]["errors"]
    assert len(errs) == 1 and errs[0]["line"] == 3 and re.search(r"onready", errs[0]["message"]), errs


def test_read_then_edit_keeps_the_users_code(session, vault_zip):
    i = session.call(P.inspect_project, {"project": str(vault_zip), "read_files": ["res://main.gd", "res://nope.gd"]})
    fc = i["data"]["file_contents"]
    assert len(fc) == 1 and fc[0]["path"] == "res://main.gd" and fc[0]["text"] == VAULT_MAIN_GD and not fc[0]["truncated"]
    assert fc[0]["lines"] == 5 and any("nope.gd" in u for u in i["uncertain"])
    w = session.call(P.write_game_files, {
        "edits": [{"path": "res://main.gd", "find": "onready var guard", "replace": "@onready var guard"},
                  {"path": "res://main.gd", "find": "var ticks := 0\n",
                   "replace": "var ticks := 0\n\n\nfunc _on_timer_timeout() -> void:\n\tticks += 1\n"}],
        "files": [{"path": "res://guard.gd", "content": "extends Node2D\n"}]})
    assert w["status"] == "ok" and w["data"]["ok"] is True, w
    assert sorted(w["data"]["written"]) == ["res://guard.gd", "res://main.gd"]
    text = (session.project / "main.gd").read_text()
    assert "@onready var guard = $Guard" in text and "var treasure_goal := 7" in text and "func _on_timer_timeout" in text
    assert session.call(K.check_project, {})["data"]["verdict"] == "ready"


def test_edit_errors_change_nothing(session, vault_zip):
    session.call(P.inspect_project, {"project": str(vault_zip)})
    before = (session.project / "main.gd").read_text()
    r = session.call(P.write_game_files, {"edits": [
        {"path": "res://main.gd", "find": "var treasure_goal := 7", "replace": "var treasure_goal := 9"},
        {"path": "res://main.gd", "find": "onready  var guard", "replace": "x"}]})
    assert r["status"] == "error" and r["error"]["code"] == "edit_text_not_found"
    assert "onready var guard = $Guard" in r["error"]["message"] and "read_files" in r["next_step"]
    assert (session.project / "main.gd").read_text() == before  # the first, valid edit was not applied either
    r = session.call(P.write_game_files, {"edits": [{"path": "res://main.gd", "find": "var ", "replace": "var  "}]})
    assert r["error"]["code"] == "edit_text_ambiguous" and "all=true" in r["next_step"]
    r = session.call(P.write_game_files, {"edits": [{"path": "res://missing.gd", "find": "a", "replace": "b"}]})
    assert r["error"]["code"] == "edit_file_missing"
    r = session.call(P.write_game_files, {"edits": [{"path": "res://main.gd", "find": "ticks", "replace": "turns", "all": True}]})
    assert r["status"] == "ok" and "var turns := 0" in (session.project / "main.gd").read_text()


def test_read_files_long_file_is_cut_and_attached(session, vault_zip):
    from conftest import output_path
    session.call(P.inspect_project, {"project": str(vault_zip)})
    long_gd = "extends Node\n" + "".join(f"var v{i} := {i}\n" for i in range(2000))
    session.call(P.write_game_files, {"files": [{"path": "res://long.gd", "content": long_gd}]})
    i = session.call(P.inspect_project, {"read_files": ["res://long.gd"]})
    fc = i["data"]["file_contents"][0]
    assert fc["truncated"] is True and len(fc["text"]) == 12_000 and fc["lines"] == 2001
    assert output_path(i, "full_0_long.gd").read_text() == long_gd
