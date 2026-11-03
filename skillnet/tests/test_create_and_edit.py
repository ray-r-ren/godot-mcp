"""create_game_project, write_game_files, edit_scenes and inspect_project on real Godot 4.4."""
import zipfile

import pytest

from conftest import output_path
from tools import project_tools as P


@pytest.mark.parametrize("starter", ["blank_2d", "top_down", "platformer", "blank_3d"])
def test_each_starter_starts_cleanly(session, starter):
    r = session.call(P.create_game_project, {"name": "Star Test", "starter": starter, "window_width": 800, "window_height": 600})
    assert r["status"] == "ok", r
    d = r["data"]
    assert d["starts_cleanly"] is True and d["errors"] == []
    assert d["main_scene"] == "res://scenes/main.tscn"
    assert "res://project.godot" in d["files"] and "res://scenes/main.tscn" in d["files"]
    assert set(d["input_actions"]) >= {"move_left", "move_right", "move_up", "move_down", "jump", "pause"}
    names = zipfile.ZipFile(output_path(r, "project.zip")).namelist()
    assert "project.godot" in names and "scenes/main.tscn" in names
    assert not any(n.startswith(".godot/") for n in names)  # the import cache is never shipped
    text = (session.project / "project.godot").read_text()
    assert 'renderer/rendering_method="gl_compatibility"' in text
    assert 'config/name="Star Test"' in text and "viewport_width=800" in text


def test_create_rejects_bad_name(session):
    r = session.call(P.create_game_project, {"name": '!!"!!'})
    assert r["status"] == "error"
    assert r["error"]["code"] == "invalid_name"
    assert "Coin Dash" in r["next_step"]


def test_write_reports_parse_error_with_line(top_down):
    good = "extends Node2D\n\nvar speed := 10\n\nfunc _process(delta: float) -> void:\n\tposition.x += speed * delta\n"
    bad = "extends Node\n\nfunc _ready():\n\tvar x = 1\n\tif x == 1\n\t\tprint('hi')\n"
    r = top_down.call(P.write_game_files, {"files": [{"path": "res://scripts/mover.gd", "content": good},
                                                     {"path": "res://scripts/bad.gd", "content": bad}]})
    assert r["status"] == "ok"
    d = r["data"]
    assert d["ok"] is False
    assert sorted(d["written"]) == ["res://scripts/bad.gd", "res://scripts/mover.gd"]
    assert len(d["script_errors"]) == 1
    e = d["script_errors"][0]
    assert e["path"] == "res://scripts/bad.gd" and e["line"] == 5 and "Expected \":\"" in e["message"]
    assert "write_game_files" in r["next_step"]
    assert (top_down.project / "scripts/mover.gd").read_text() == good
    # Delete them again; the project is back to compiling.
    r = top_down.call(P.write_game_files, {"files": [], "delete": ["res://scripts/bad.gd", "res://scripts/mover.gd"]})
    assert r["data"]["ok"] is True and len(r["data"]["deleted"]) == 2
    assert not (top_down.project / "scripts/bad.gd").exists()


def test_write_flags_godot3_syntax(top_down):
    old = "extends KinematicBody2D\n\nonready var sprite = $Sprite\n"
    r = top_down.call(P.write_game_files, {"files": [{"path": "res://scripts/old.gd", "content": old}]})
    errs = r["data"]["script_errors"]
    assert errs and errs[0]["line"] == 3 and "onready" in errs[0]["message"]
    top_down.call(P.write_game_files, {"files": [], "delete": ["res://scripts/old.gd"]})


@pytest.mark.parametrize("path", ["../outside.gd", "res://../../etc/passwd", "/etc/passwd"])
def test_write_rejects_paths_outside_project(top_down, path):
    r = top_down.call(P.write_game_files, {"files": [{"path": path, "content": "x"}]})
    assert r["status"] == "error" and r["error"]["code"] == "invalid_path"
    assert "res://" in r["next_step"]


def test_write_without_project_errors(session):
    r = session.call(P.write_game_files, {"files": [{"path": "res://a.gd", "content": "extends Node\n"}]})
    assert r["status"] == "error" and r["error"]["code"] == "no_project"
    assert "state_id" in r["next_step"]


def test_edit_scenes_persists_nodes_signals_and_actions(top_down):
    ops = [
        {"op": "add_node", "scene": "res://scenes/main.tscn", "parent": ".", "type": "Timer", "name": "SpawnTimer",
         "properties": {"wait_time": 2, "autostart": True}},
        {"op": "add_node", "scene": "res://scenes/main.tscn", "parent": "HUD", "type": "Label", "name": "Hint",
         "properties": {"text": "Collect coins!", "position": [20, 600]}},
        {"op": "connect_signal", "scene": "res://scenes/main.tscn", "node": "SpawnTimer", "signal": "timeout",
         "target": ".", "method": "_on_spawn_timer_timeout"},
        {"op": "add_input_action", "name": "dash", "keys": ["Shift", "mouse_right"]},
        {"op": "instantiate_scene", "scene": "res://scenes/main.tscn", "child_scene": "res://scenes/coin.tscn",
         "parent": "Coins", "name": "Coin6", "properties": {"position": [700, 600]}},
    ]
    r = top_down.call(P.edit_scenes, {"operations": ops})
    assert r["status"] == "ok", r
    assert r["data"]["applied"] == 5 and r["data"]["failed_op"] is None
    assert "has no method" in r["data"]["results"][2]["message"]  # warned, not refused
    tscn = (top_down.project / "scenes/main.tscn").read_text()
    assert '[node name="SpawnTimer" type="Timer" parent="."]' in tscn and "wait_time = 2.0" in tscn
    assert '[connection signal="timeout" from="SpawnTimer" to="." method="_on_spawn_timer_timeout"' in tscn
    assert 'name="Coin6"' in tscn and "Vector2(700, 600)" in tscn
    # Reloaded independently by inspect_project.
    i = top_down.call(P.inspect_project, {"detail": "full"})
    main = next(s for s in i["data"]["scenes"] if s["path"] == "res://scenes/main.tscn")
    tree = "\n".join(main["tree"])
    assert "SpawnTimer (Timer)" in tree and "Hint (Label)" in tree and "Coin6 (instance of res://scenes/coin.tscn)" in tree
    assert i["data"]["input_actions"]["dash"] == ["Shift", "mouse_right"]
    # Add the handler so later checks in this module see a clean project.
    main_gd = (top_down.project / "scripts/main.gd").read_text() + "\n\nfunc _on_spawn_timer_timeout() -> void:\n\tpass\n"
    w = top_down.call(P.write_game_files, {"files": [{"path": "res://scripts/main.gd", "content": main_gd}]})
    assert w["data"]["ok"] is True


def test_edit_scenes_bad_parent_saves_nothing(top_down):
    before = (top_down.project / "scenes/main.tscn").read_text()
    ops = [
        {"op": "add_node", "scene": "res://scenes/main.tscn", "parent": ".", "type": "Sprite2D", "name": "Fine"},
        {"op": "add_node", "scene": "res://scenes/main.tscn", "parent": "NoSuchNode", "type": "Sprite2D", "name": "S"},
    ]
    r = top_down.call(P.edit_scenes, {"operations": ops})
    assert r["status"] == "partial"
    assert r["data"]["failed_op"] == 1 and r["data"]["applied"] == 1
    msg = r["data"]["results"][1]["message"]
    assert "NoSuchNode" in msg and "Player" in msg  # names the real nodes
    assert (top_down.project / "scenes/main.tscn").read_text() == before
    assert "operation 1" in r["next_step"].lower()


def test_edit_scenes_missing_field_is_an_error(top_down):
    r = top_down.call(P.edit_scenes, {"operations": [{"op": "add_node", "scene": "res://scenes/main.tscn", "parent": "."}]})
    assert r["status"] == "error" and r["error"]["code"] == "invalid_operation"
    assert "missing: type" in r["error"]["message"]
    assert "operation 0" in r["next_step"]


def test_inspect_uploaded_project(session, red_project_zip):
    r = session.call(P.inspect_project, {"project": str(red_project_zip)})
    assert r["status"] == "ok", r
    d = r["data"]
    assert d["project_name"] == "Red Coin" and d["config_version"] == 5
    assert d["renderer"] == "gl_compatibility" and d["main_scene"] == "res://main.tscn"
    scripts = {s["path"]: s for s in d["scripts"]}
    assert set(scripts) == {"res://main.gd", "res://player.gd", "res://coin.gd"}
    assert "_on_collected()" in scripts["res://main.gd"]["methods"]
    assert scripts["res://coin.gd"]["signals"] == ["collected"]
    assert scripts["res://player.gd"]["exports"] == ["speed := 200.0"]
    assert d["input_actions"]["move_right"] == ["D"]
    main = next(s for s in d["scenes"] if s["path"] == "res://main.tscn")
    assert main["root_type"] == "Node2D" and main["node_count"] == 6
    assert output_path(r, "project_map.json").stat().st_size > 100


def test_inspect_refuses_godot3(session, godot3_zip):
    r = session.call(P.inspect_project, {"project": str(godot3_zip)})
    assert r["status"] == "error" and r["error"]["code"] == "godot3_project"
    assert "create_game_project" in r["next_step"]
