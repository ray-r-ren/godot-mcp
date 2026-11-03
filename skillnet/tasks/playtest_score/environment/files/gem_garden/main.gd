extends Node2D
## Gem Garden: gems are worth their value; in the lower meadow (below y = 400) they count double.

var score := 0


func _ready() -> void:
	for gem in get_tree().get_nodes_in_group("gems"):
		gem.picked.connect(_on_gem_picked)


func _on_gem_picked(value: int, where: Vector2) -> void:
	var bonus := 2 if where.y > 400.0 else 1
	score += value * bonus
	$HUD/ScoreLabel.text = "Score: %d" % score
