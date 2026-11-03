"""Fixtures: small Godot 4 projects written as text and zipped at test time (deterministic)."""
import pathlib
import shutil
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skillnet_sdk import call_tool  # noqa: E402

PROJECT_GODOT = """config_version=5

[application]
config/name="{name}"
run/main_scene="res://main.tscn"

[display]
window/size/viewport_width=640
window/size/viewport_height=360

[input]
move_right={{
"deadzone": 0.5,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":68,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]
}}

[rendering]
renderer/rendering_method="gl_compatibility"
"""

# A red full-screen background, a player that moves right on move_right, one coin in its path and a score.
RED_MAIN_TSCN = """[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]
[ext_resource type="Script" path="res://player.gd" id="2"]
[ext_resource type="Script" path="res://coin.gd" id="3"]

[sub_resource type="RectangleShape2D" id="shape_p"]
size = Vector2(24, 24)

[sub_resource type="CircleShape2D" id="shape_c"]
radius = 10.0

[node name="Main" type="Node2D"]
script = ExtResource("1")

[node name="Background" type="ColorRect" parent="."]
offset_right = 640.0
offset_bottom = 360.0
color = Color(0.9, 0.1, 0.1, 1)

[node name="Player" type="CharacterBody2D" parent="." groups=["player"]]
position = Vector2(100, 180)
script = ExtResource("2")

[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]
shape = SubResource("shape_p")

[node name="Coin" type="Area2D" parent="."]
position = Vector2(220, 180)
script = ExtResource("3")

[node name="CollisionShape2D" type="CollisionShape2D" parent="Coin"]
shape = SubResource("shape_c")
"""

MAIN_GD = """extends Node2D

var score := 0


func _ready() -> void:
	$Coin.collected.connect(_on_collected)


func _on_collected() -> void:
	score += 10
"""

PLAYER_GD = """extends CharacterBody2D

@export var speed := 200.0


func _physics_process(_delta: float) -> void:
	velocity = Vector2(Input.get_axis("ui_left", "move_right") * speed, 0)
	move_and_slide()
"""

COIN_GD = """extends Area2D

signal collected


func _ready() -> void:
	body_entered.connect(_on_body)


func _on_body(body: Node) -> void:
	if body.is_in_group("player"):
		collected.emit()
		queue_free()
"""

# Broken: a syntax error in one script and a scene pointing at a script that doesn't exist.
BROKEN_MAIN_TSCN = """[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]
[ext_resource type="Script" path="res://missing_enemy.gd" id="2"]

[node name="Main" type="Node2D"]
script = ExtResource("1")

[node name="Enemy" type="Node2D" parent="."]
script = ExtResource("2")
"""

BROKEN_MAIN_GD = """extends Node2D

var lives := 3


func _ready() -> void:
	if lives > 0
		print("alive")
"""

CRASH_MAIN_TSCN = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]

[node name="Main" type="ColorRect"]
offset_right = 640.0
offset_bottom = 360.0
color = Color(0, 0, 1, 1)
script = ExtResource("1")
"""

CRASH_MAIN_GD = """extends ColorRect

var t := 0.0


func _process(delta: float) -> void:
	t += delta
	if t > 0.5:
		var enemy = null
		enemy.position = Vector2(1, 1)
"""


def write_project(dest: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    dest.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return dest


def zip_dir(src: pathlib.Path, zpath: pathlib.Path, top: str | None = None) -> pathlib.Path:
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                arc = p.relative_to(src).as_posix()
                zf.write(p, f"{top}/{arc}" if top else arc)
    return zpath


@pytest.fixture(scope="session")
def red_project_zip(tmp_path_factory) -> pathlib.Path:
    d = tmp_path_factory.mktemp("red")
    src = write_project(d / "src", {"project.godot": PROJECT_GODOT.format(name="Red Coin"), "main.tscn": RED_MAIN_TSCN,
                                    "main.gd": MAIN_GD, "player.gd": PLAYER_GD, "coin.gd": COIN_GD})
    # Inside a top folder, as people usually zip a project folder.
    return zip_dir(src, d / "red_coin.zip", top="red_coin")


@pytest.fixture(scope="session")
def broken_project_zip(tmp_path_factory) -> pathlib.Path:
    d = tmp_path_factory.mktemp("broken")
    src = write_project(d / "src", {"project.godot": PROJECT_GODOT.format(name="Broken"), "main.tscn": BROKEN_MAIN_TSCN,
                                    "main.gd": BROKEN_MAIN_GD})
    return zip_dir(src, d / "broken.zip")


@pytest.fixture(scope="session")
def crash_project_zip(tmp_path_factory) -> pathlib.Path:
    d = tmp_path_factory.mktemp("crash")
    src = write_project(d / "src", {"project.godot": PROJECT_GODOT.format(name="Crash"), "main.tscn": CRASH_MAIN_TSCN,
                                    "main.gd": CRASH_MAIN_GD})
    return zip_dir(src, d / "crash.zip")


@pytest.fixture(scope="session")
def godot3_zip(tmp_path_factory) -> pathlib.Path:
    d = tmp_path_factory.mktemp("g3")
    src = write_project(d / "src", {"project.godot": 'config_version=4\n\n[application]\nconfig/name="Old"\n'})
    return zip_dir(src, d / "old.zip")


class Session:
    """Runs tools one after another on the same state directory, like an agent passing a state_id."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.state = root / "state"
        self.out = root / "out"
        self.out.mkdir(parents=True, exist_ok=True)

    def call(self, fn, args: dict, fresh: bool = False) -> dict:
        if fresh and self.state.exists():
            shutil.rmtree(self.state)
        return as_dict(call_tool(fn, args, output_root=self.out, state_dir=self.state))

    @property
    def project(self) -> pathlib.Path:
        return self.state / "project"


@pytest.fixture
def session(tmp_path) -> Session:
    return Session(tmp_path)


@pytest.fixture(scope="module")
def top_down(tmp_path_factory) -> Session:
    """One top_down project per test module, created once (creation imports and runs the game)."""
    from tools import project_tools as P
    s = Session(tmp_path_factory.mktemp("topdown"))
    r = s.call(P.create_game_project, {"name": "Coin Dash", "starter": "top_down"})
    assert r["status"] == "ok", r
    return s


def as_dict(envelope) -> dict:
    return envelope if isinstance(envelope, dict) else envelope.model_dump()


def output_path(result: dict, name: str) -> pathlib.Path:
    for o in result["outputs"]:
        if o["name"] == name:
            return pathlib.Path(o["path"])
    raise AssertionError(f"no output {name}: {[o['name'] for o in result['outputs']]}")
