#!/bin/bash
set -e
# Oracle: write the Godot 4 project by hand and zip it (no skill tools).
set -euo pipefail
P=$(mktemp -d)/coin_rush
mkdir -p "$P" /task/outputs
cat > "$P/project.godot" <<'G'
config_version=5

[application]
config/name="Coin Rush"
run/main_scene="res://main.tscn"

[display]
window/size/viewport_width=960
window/size/viewport_height=540

[input]
move_left={"deadzone": 0.5, "events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194319,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":65,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]}
move_right={"deadzone": 0.5, "events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194321,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":68,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]}
move_up={"deadzone": 0.5, "events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194320,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":87,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]}
move_down={"deadzone": 0.5, "events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194322,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null), Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":83,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)]}

[rendering]
renderer/rendering_method="gl_compatibility"
G
cat > "$P/main.gd" <<'G'
extends Node2D

var score := 0
var total := 0


func _ready() -> void:
	var positions := [Vector2(700, 270), Vector2(200, 100), Vector2(800, 450), Vector2(300, 440), Vector2(480, 80)]
	for p in positions:
		var coin := Area2D.new()
		coin.position = p
		coin.add_to_group("coins")
		var shape := CollisionShape2D.new()
		var circle := CircleShape2D.new()
		circle.radius = 12
		shape.shape = circle
		coin.add_child(shape)
		var look := ColorRect.new()
		look.color = Color(1, 0.85, 0.2)
		look.size = Vector2(24, 24)
		look.position = Vector2(-12, -12)
		coin.add_child(look)
		coin.body_entered.connect(_on_coin_body_entered.bind(coin))
		add_child(coin)
		total += 1


func _on_coin_body_entered(body: Node, coin: Area2D) -> void:
	if body.is_in_group("player") and not coin.is_queued_for_deletion():
		coin.queue_free()
		score += 1
		$HUD/Score.text = "Score: %d" % score
		if score == total:
			$HUD/Win.visible = true
G
cat > "$P/player.gd" <<'G'
extends CharacterBody2D


func _physics_process(_delta: float) -> void:
	velocity = Input.get_vector("move_left", "move_right", "move_up", "move_down") * 280.0
	move_and_slide()
G
cat > "$P/main.tscn" <<'G'
[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]
[ext_resource type="Script" path="res://player.gd" id="2"]

[sub_resource type="RectangleShape2D" id="s"]
size = Vector2(24, 24)

[node name="Main" type="Node2D"]
script = ExtResource("1")

[node name="Bg" type="ColorRect" parent="."]
offset_right = 960.0
offset_bottom = 540.0
color = Color(0.1, 0.12, 0.2, 1)

[node name="Player" type="CharacterBody2D" parent="." groups=["player"]]
position = Vector2(480, 270)
script = ExtResource("2")

[node name="Look" type="ColorRect" parent="Player"]
offset_left = -12.0
offset_top = -12.0
offset_right = 12.0
offset_bottom = 12.0
color = Color(0.3, 0.6, 1, 1)

[node name="Shape" type="CollisionShape2D" parent="Player"]
shape = SubResource("s")

[node name="HUD" type="CanvasLayer" parent="."]

[node name="Score" type="Label" parent="HUD"]
offset_left = 12.0
offset_top = 8.0
text = "Score: 0"

[node name="Win" type="Label" parent="HUD"]
visible = false
offset_left = 400.0
offset_top = 250.0
text = "You win!"
G
cd "$P" && python3 -c "
import zipfile, pathlib
with zipfile.ZipFile('/task/outputs/coin_rush.zip', 'w') as z:
    for p in sorted(pathlib.Path('.').rglob('*')):
        if p.is_file(): z.write(p, p.as_posix())
"
