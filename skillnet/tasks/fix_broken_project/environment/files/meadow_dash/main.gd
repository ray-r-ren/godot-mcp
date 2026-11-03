extends Node2D

var score = 0


func _ready():
	for c in get_tree().get_nodes_in_group("coins"):
		c.connect("collected", self, "_on_coin_collected")


func _on_coin_collected(value):
	score += value
	$HUD/ScoreLabel.text = "Score: " + str(score)
