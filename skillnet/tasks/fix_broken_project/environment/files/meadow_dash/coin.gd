extends Area2D

signal collected(value)

export var value = 1


func _ready():
	connect("body_entered", self, "_on_body_entered")


func _on_body_entered(body):
	if body.is_in_group("player"):
		emit_signal("collected", value)
		queue_free()
