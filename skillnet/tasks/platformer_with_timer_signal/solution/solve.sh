#!/bin/bash
set -e
# Oracle: write the Godot 4 project by hand, check it compiles with Godot directly, and zip it (no skill tools).
set -euo pipefail
W=$(mktemp -d); P="$W/tower_climb"; mkdir -p "$P" /task/outputs
K='Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":%s,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)'
key() { printf "$K" "$1"; }
cat > "$P/project.godot" <<G
config_version=5

[application]
config/name="Tower Climb"
run/main_scene="res://main.tscn"

[input]
move_left={"deadzone": 0.5, "events": [$(key 4194319)]}
move_right={"deadzone": 0.5, "events": [$(key 4194321)]}
jump={"deadzone": 0.5, "events": [$(key 32)]}

[rendering]
renderer/rendering_method="gl_compatibility"
G
cat > "$P/main.gd" <<'G'
extends Node2D

var time_left := 60


func _ready() -> void:
	$TimeLabel.text = "Time: %d" % time_left


func _on_countdown_timeout() -> void:
	time_left -= 1
	$TimeLabel.text = "Time: %d" % time_left
G
cat > "$P/player.gd" <<'G'
extends CharacterBody2D

const SPEED := 250.0
const JUMP := -450.0
const GRAVITY := 1200.0


func _physics_process(delta: float) -> void:
	velocity.y += GRAVITY * delta
	if is_on_floor() and Input.is_action_just_pressed("jump"):
		velocity.y = JUMP
	velocity.x = Input.get_axis("move_left", "move_right") * SPEED
	move_and_slide()
G
cat > "$P/main.tscn" <<'G'
[gd_scene load_steps=5 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]
[ext_resource type="Script" path="res://player.gd" id="2"]

[sub_resource type="RectangleShape2D" id="p"]
size = Vector2(24, 32)

[sub_resource type="RectangleShape2D" id="f"]
size = Vector2(1200, 40)

[node name="Main" type="Node2D"]
script = ExtResource("1")

[node name="Floor" type="StaticBody2D" parent="."]
position = Vector2(576, 600)

[node name="CollisionShape2D" type="CollisionShape2D" parent="Floor"]
shape = SubResource("f")

[node name="Player" type="CharacterBody2D" parent="."]
position = Vector2(200, 540)
script = ExtResource("2")

[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]
shape = SubResource("p")

[node name="TimeLabel" type="Label" parent="."]
offset_left = 16.0
offset_top = 16.0
text = "Time: 60"

[node name="Countdown" type="Timer" parent="."]
autostart = true

[connection signal="timeout" from="Countdown" to="." method="_on_countdown_timeout"]
G
export HOME=$(mktemp -d)
godot --headless --path "$P" --import >/dev/null 2>&1 || true
for s in main.gd player.gd; do godot --headless --path "$P" --check-only --script "res://$s"; done
(cd "$W" && rm -rf tower_climb/.godot && python3 -c "import shutil; shutil.make_archive('/task/outputs/tower_climb', 'zip', '$W', 'tower_climb')")
echo "Tower Climb project: /task/outputs/tower_climb.zip" > /task/answer.txt
