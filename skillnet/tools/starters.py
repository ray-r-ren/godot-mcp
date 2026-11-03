"""Starter Godot 4.4 projects written as plain text (simple shapes and colours, no binary assets)."""

from __future__ import annotations

KEY = {
    "A": 65, "D": 68, "W": 87, "S": 83, "P": 80,
    "Space": 32, "Escape": 4194305, "Left": 4194319, "Up": 4194320, "Right": 4194321, "Down": 4194322,
}

INPUT_ACTIONS: dict[str, list[str]] = {
    "move_left": ["A", "Left"],
    "move_right": ["D", "Right"],
    "move_up": ["W", "Up"],
    "move_down": ["S", "Down"],
    "jump": ["Space", "W", "Up"],
    "pause": ["Escape", "P"],
}


def key_event(name: str) -> str:
    code = KEY[name]
    return (
        'Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,'
        '"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,'
        '"meta_pressed":false,"pressed":false,"keycode":0,'
        f'"physical_keycode":{code},"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)'
    )


def input_section(actions: dict[str, list[str]]) -> str:
    out = ["[input]", ""]
    for name, keys in actions.items():
        events = ", ".join(key_event(k) for k in keys)
        out.append(f'{name}={{\n"deadzone": 0.2,\n"events": [{events}]\n}}')
    return "\n".join(out) + "\n"


def project_godot(name: str, width: int, height: int, three_d: bool, clear: str) -> str:
    safe = name.replace("\\", "").replace('"', "'")
    return f"""; Engine configuration file.
; Created by Instant Game Studio for Godot 4.4.

config_version=5

[application]

config/name="{safe}"
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.4", "GL Compatibility")

[display]

window/size/viewport_width={width}
window/size/viewport_height={height}
window/stretch/mode="{'disabled' if three_d else 'canvas_items'}"

{input_section(INPUT_ACTIONS)}
[rendering]

renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
environment/defaults/default_clear_color={clear}
"""


MAIN_GD_2D = """extends Node2D
## Main scene: keeps the score and updates the HUD.

var score := 0

@onready var score_label: Label = $HUD/ScoreLabel


func _ready() -> void:
	for coin in get_tree().get_nodes_in_group("coins"):
		coin.collected.connect(_on_coin_collected)


func _on_coin_collected(value: int) -> void:
	score += value
	score_label.text = "Score: %d" % score
"""

COIN_GD = """extends Area2D
## A collectible. Emits `collected` and disappears when the player touches it.

signal collected(value: int)

@export var value := 1


func _ready() -> void:
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node2D) -> void:
	if body.is_in_group("player"):
		collected.emit(value)
		queue_free()
"""

COIN_TSCN = """[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path="res://scripts/coin.gd" id="1_coin"]

[sub_resource type="CircleShape2D" id="CircleShape2D_coin"]
radius = 14.0

[node name="Coin" type="Area2D" groups=["coins"]]
script = ExtResource("1_coin")

[node name="Visual" type="Polygon2D" parent="."]
color = Color(1, 0.84, 0.15, 1)
polygon = PackedVector2Array(0, -14, 10, -10, 14, 0, 10, 10, 0, 14, -10, 10, -14, 0, -10, -10)

[node name="CollisionShape2D" type="CollisionShape2D" parent="."]
shape = SubResource("CircleShape2D_coin")
"""

PLAYER_TOPDOWN_GD = """extends CharacterBody2D
## Top-down player: moves in 8 directions with move_left/right/up/down and stays on screen.

@export var speed := 300.0


func _physics_process(_delta: float) -> void:
	var direction := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	velocity = direction * speed
	move_and_slide()
	var view := get_viewport_rect().size
	position = position.clamp(Vector2(16, 16), view - Vector2(16, 16))
"""

PLAYER_PLATFORMER_GD = """extends CharacterBody2D
## Side-view player: runs with move_left/move_right, jumps with jump, falls with gravity.

@export var speed := 260.0
@export var jump_velocity := -560.0

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
var spawn_point := Vector2.ZERO


func _ready() -> void:
	spawn_point = position


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y += gravity * delta
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = jump_velocity
	velocity.x = Input.get_axis("move_left", "move_right") * speed
	move_and_slide()
	if position.y > get_viewport_rect().size.y + 200:
		position = spawn_point
		velocity = Vector2.ZERO
"""

PLAYER_2D_TSCN = """[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path="res://scripts/player.gd" id="1_player"]

[sub_resource type="RectangleShape2D" id="RectangleShape2D_player"]
size = Vector2(32, 32)

[node name="Player" type="CharacterBody2D" groups=["player"]]
script = ExtResource("1_player")

[node name="Visual" type="ColorRect" parent="."]
offset_left = -16.0
offset_top = -16.0
offset_right = 16.0
offset_bottom = 16.0
color = Color(0.25, 0.6, 1, 1)

[node name="CollisionShape2D" type="CollisionShape2D" parent="."]
shape = SubResource("RectangleShape2D_player")
"""


def _hud(title: str) -> str:
    return f"""
[node name="HUD" type="CanvasLayer" parent="."]

[node name="ScoreLabel" type="Label" parent="HUD"]
offset_left = 16.0
offset_top = 12.0
offset_right = 400.0
offset_bottom = 52.0
theme_override_font_sizes/font_size = 28
text = "{title}"
"""


def topdown_main(w: int, h: int) -> str:
    coins = ""
    pts = [(0.72, 0.5), (0.28, 0.5), (0.5, 0.22), (0.5, 0.78), (0.85, 0.2)]
    for i, (fx, fy) in enumerate(pts, 1):
        coins += f'\n[node name="Coin{i}" parent="Coins" instance=ExtResource("3_coin")]\nposition = Vector2({int(w*fx)}, {int(h*fy)})\n'
    return f"""[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1_main"]
[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="2_player"]
[ext_resource type="PackedScene" path="res://scenes/coin.tscn" id="3_coin"]

[node name="Main" type="Node2D"]
script = ExtResource("1_main")

[node name="Background" type="ColorRect" parent="."]
offset_right = {w}.0
offset_bottom = {h}.0
color = Color(0.12, 0.16, 0.22, 1)

[node name="Coins" type="Node2D" parent="."]
{coins}
[node name="Player" parent="." instance=ExtResource("2_player")]
position = Vector2({w//2}, {h//2})
{_hud("Score: 0")}"""


def platformer_main(w: int, h: int) -> str:
    plats = [("Ground", w / 2, h - 28, w, 56), ("LedgeLeft", w * 0.25, h * 0.68, 240, 24),
             ("LedgeRight", w * 0.72, h * 0.5, 240, 24)]
    subs, nodes = "", ""
    for i, (name, x, y, pw, ph) in enumerate(plats, 1):
        subs += f'\n[sub_resource type="RectangleShape2D" id="RectangleShape2D_{i}"]\nsize = Vector2({pw}, {ph})\n'
        nodes += f"""
[node name="{name}" type="StaticBody2D" parent="Level"]
position = Vector2({int(x)}, {int(y)})

[node name="Visual" type="ColorRect" parent="Level/{name}"]
offset_left = {-pw/2}
offset_top = {-ph/2}
offset_right = {pw/2}
offset_bottom = {ph/2}
color = Color(0.3, 0.75, 0.35, 1)

[node name="CollisionShape2D" type="CollisionShape2D" parent="Level/{name}"]
shape = SubResource("RectangleShape2D_{i}")
"""
    coins = ""
    pts = [(w * 0.25, h * 0.68 - 40), (w * 0.72, h * 0.5 - 40), (w * 0.62, h - 80), (w * 0.85, h - 80)]
    for i, (x, y) in enumerate(pts, 1):
        coins += f'\n[node name="Coin{i}" parent="Coins" instance=ExtResource("3_coin")]\nposition = Vector2({int(x)}, {int(y)})\n'
    return f"""[gd_scene load_steps=7 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1_main"]
[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="2_player"]
[ext_resource type="PackedScene" path="res://scenes/coin.tscn" id="3_coin"]
{subs}
[node name="Main" type="Node2D"]
script = ExtResource("1_main")

[node name="Background" type="ColorRect" parent="."]
offset_right = {w}.0
offset_bottom = {h}.0
color = Color(0.45, 0.7, 0.95, 1)

[node name="Level" type="Node2D" parent="."]
{nodes}
[node name="Coins" type="Node2D" parent="."]
{coins}
[node name="Player" parent="." instance=ExtResource("2_player")]
position = Vector2({int(w*0.12)}, {h - 100})
{_hud("Score: 0")}"""


BLANK2D_GD = """extends Node2D
## Main scene of a blank 2D game. Add your nodes and logic here.


func _ready() -> void:
	pass
"""


def blank2d_main(w: int, h: int, title: str) -> str:
    safe = title.replace('"', "'")
    return f"""[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1_main"]

[node name="Main" type="Node2D"]
script = ExtResource("1_main")

[node name="Background" type="ColorRect" parent="."]
offset_right = {w}.0
offset_bottom = {h}.0
color = Color(0.1, 0.1, 0.14, 1)

[node name="Title" type="Label" parent="."]
offset_left = 0.0
offset_top = {h//2 - 30}.0
offset_right = {w}.0
offset_bottom = {h//2 + 30}.0
theme_override_font_sizes/font_size = 40
text = "{safe}"
horizontal_alignment = 1
vertical_alignment = 1
"""


PLAYER_3D_GD = """extends CharacterBody3D
## 3D player: moves on the ground with move_* actions, jumps with jump.

@export var speed := 6.0
@export var jump_velocity := 6.5

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= gravity * delta
	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = jump_velocity
	var input := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	velocity.x = input.x * speed
	velocity.z = input.y * speed
	move_and_slide()
	if position.y < -20.0:
		position = Vector3(0, 1, 0)
		velocity = Vector3.ZERO
"""

MAIN_3D_GD = """extends Node3D
## Main scene of a 3D game. The camera looks at the arena from above.


func _ready() -> void:
	$Camera3D.look_at(Vector3.ZERO, Vector3.UP)
"""

MAIN_3D_TSCN = """[gd_scene load_steps=10 format=3]

[ext_resource type="Script" path="res://scripts/main.gd" id="1_main"]
[ext_resource type="Script" path="res://scripts/player.gd" id="2_player"]

[sub_resource type="Environment" id="Environment_1"]
background_mode = 1
background_color = Color(0.5, 0.7, 0.9, 1)
ambient_light_source = 2
ambient_light_color = Color(0.6, 0.6, 0.65, 1)

[sub_resource type="BoxShape3D" id="BoxShape3D_ground"]
size = Vector3(20, 1, 20)

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_ground"]
albedo_color = Color(0.3, 0.7, 0.35, 1)

[sub_resource type="BoxMesh" id="BoxMesh_ground"]
material = SubResource("StandardMaterial3D_ground")
size = Vector3(20, 1, 20)

[sub_resource type="CapsuleShape3D" id="CapsuleShape3D_player"]

[sub_resource type="StandardMaterial3D" id="StandardMaterial3D_player"]
albedo_color = Color(0.25, 0.5, 1, 1)

[sub_resource type="CapsuleMesh" id="CapsuleMesh_player"]
material = SubResource("StandardMaterial3D_player")

[node name="Main" type="Node3D"]
script = ExtResource("1_main")

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Environment_1")

[node name="Sun" type="DirectionalLight3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0.5, 0.866, 0, -0.866, 0.5, 0, 10, 0)

[node name="Camera3D" type="Camera3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 9, 12)
current = true

[node name="Ground" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -0.5, 0)

[node name="Mesh" type="MeshInstance3D" parent="Ground"]
mesh = SubResource("BoxMesh_ground")

[node name="CollisionShape3D" type="CollisionShape3D" parent="Ground"]
shape = SubResource("BoxShape3D_ground")

[node name="Player" type="CharacterBody3D" parent="." groups=["player"]]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0)
script = ExtResource("2_player")

[node name="Mesh" type="MeshInstance3D" parent="Player"]
mesh = SubResource("CapsuleMesh_player")

[node name="CollisionShape3D" type="CollisionShape3D" parent="Player"]
shape = SubResource("CapsuleShape3D_player")
"""

GITIGNORE = ".godot/\n/android/\n"

STARTERS = ("blank_2d", "top_down", "platformer", "blank_3d")


def build_starter(starter: str, name: str, width: int, height: int) -> dict[str, str]:
    """Return {relative path: text} for a starter project."""
    files: dict[str, str] = {".gitignore": GITIGNORE}
    if starter == "blank_3d":
        files["project.godot"] = project_godot(name, width, height, True, "Color(0.5, 0.7, 0.9, 1)")
        files["scenes/main.tscn"] = MAIN_3D_TSCN
        files["scripts/main.gd"] = MAIN_3D_GD
        files["scripts/player.gd"] = PLAYER_3D_GD
        return files
    files["project.godot"] = project_godot(name, width, height, False, "Color(0.1, 0.1, 0.14, 1)")
    if starter == "blank_2d":
        files["scenes/main.tscn"] = blank2d_main(width, height, name)
        files["scripts/main.gd"] = BLANK2D_GD
        return files
    files["scripts/main.gd"] = MAIN_GD_2D
    files["scripts/coin.gd"] = COIN_GD
    files["scenes/coin.tscn"] = COIN_TSCN
    files["scenes/player.tscn"] = PLAYER_2D_TSCN
    if starter == "top_down":
        files["scripts/player.gd"] = PLAYER_TOPDOWN_GD
        files["scenes/main.tscn"] = topdown_main(width, height)
    else:
        files["scripts/player.gd"] = PLAYER_PLATFORMER_GD
        files["scenes/main.tscn"] = platformer_main(width, height)
    return files
