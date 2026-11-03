extends CharacterBody2D

@export var speed := 160.0


func _physics_process(_delta: float) -> void:
	var dir := Vector2.ZERO
	dir.x = Input.get_axis("ui_left", "ui_right")
	if Input.is_action_pressed("ui_up")
		dir.y = -1.0
	velocity = dir * speed
	move_and_slide()
