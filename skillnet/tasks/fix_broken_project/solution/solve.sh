#!/bin/bash
set -e
# Oracle: port the scripts to Godot 4 by hand, drop the missing music script, zip the result.
set -euo pipefail
W=$(mktemp -d)
python3 - "$W" <<'PY'
import sys, zipfile, pathlib
w = pathlib.Path(sys.argv[1])
zipfile.ZipFile("/task/inputs/meadow_dash.zip").extractall(w)
p = w / "meadow_dash"
(p / "main.gd").write_text('''extends Node2D

var score := 0


func _ready() -> void:
	for c in get_tree().get_nodes_in_group("coins"):
		c.collected.connect(_on_coin_collected)


func _on_coin_collected(value: int) -> void:
	score += value
	$HUD/ScoreLabel.text = "Score: " + str(score)
''')
(p / "player.gd").write_text('''extends CharacterBody2D

@export var speed := 220.0
@onready var look = $Look


func _physics_process(_delta: float) -> void:
	velocity = Input.get_vector("move_left", "move_right", "move_up", "move_down") * speed
	move_and_slide()
''')
(p / "coin.gd").write_text('''extends Area2D

signal collected(value: int)

@export var value := 1


func _ready() -> void:
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		collected.emit(value)
		queue_free()
''')
t = (p / "main.tscn").read_text()
t = t.replace('[ext_resource type="Script" path="res://music.gd" id="4"]\n', "").replace("load_steps=7", "load_steps=6")
t = t.replace('[node name="Music" type="Node" parent="."]\nscript = ExtResource("4")\n\n', "")
t = t.replace('type="KinematicBody2D"', 'type="CharacterBody2D"')
(p / "main.tscn").write_text(t)
pathlib.Path("/task/outputs").mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile("/task/outputs/meadow_dash_fixed.zip", "w") as z:
    for f in sorted(p.rglob("*")):
        if f.is_file():
            z.write(f, "meadow_dash/" + f.relative_to(p).as_posix())
PY
