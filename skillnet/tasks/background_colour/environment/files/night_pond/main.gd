extends Node2D

# Night falls over the pond: the sky colour is chosen when the game starts.
const DUSK_HUE := 0.6
const DUSK_SATURATION := 0.7
const DUSK_VALUE := 0.5

func _ready() -> void:
	$Background.color = Color.from_hsv(DUSK_HUE, DUSK_SATURATION, DUSK_VALUE)

func _process(delta: float) -> void:
	$Pad1.rotation += delta * 0.2
	$Pad2.rotation -= delta * 0.15
