extends Node2D

var t := 0.0

func _process(delta: float) -> void:
	t += delta
	$Star.position.y = 225.0 - absf(sin(t * 3.0)) * 80.0
	$Star.rotation = sin(t) * 0.3
