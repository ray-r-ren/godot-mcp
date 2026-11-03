extends Area2D

signal picked(value: int, where: Vector2)

@export var value := 1


func _ready() -> void:
	body_entered.connect(_on_body_entered)
	$Look.color = Color(0.3, 0.9, 0.5) if value < 5 else Color(0.9, 0.3, 0.9)


func _on_body_entered(body: Node) -> void:
	if body.is_in_group("player"):
		picked.emit(value, global_position)
		queue_free()
