extends KinematicBody2D

export var speed = 220
onready var look = $Look


func _physics_process(delta):
	var dir = Vector2.ZERO
	if Input.is_action_pressed("move_right"):
		dir.x += 1
	if Input.is_action_pressed("move_left"):
		dir.x -= 1
	if Input.is_action_pressed("move_down"):
		dir.y += 1
	if Input.is_action_pressed("move_up"):
		dir.y -= 1
	move_and_slide(dir.normalized() * speed)
