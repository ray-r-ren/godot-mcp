extends Node
## Independent checker injected as an autoload: measures movement, coin pickup and score, then prints JSON.

var _f := 0
var _phase := 0
var _player: Node = null
var _start_x := 0.0
var _coins: Array = []
var _coin_i := 0
var _r := {"moved": 0.0, "coins": 0, "coins_initial": 0, "score_start": null, "score_before_pickups": null, "score_after_one": null, "score_end": null, "win_text": false, "player": false, "notes": []}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


func _find_player(n: Node) -> Node:
	var g := get_tree().get_nodes_in_group("player")
	if not g.is_empty():
		return g[0]
	return n.find_child("Player", true, false)


func _texts_with_win(n: Node) -> bool:
	if (n is Label or n is RichTextLabel or n is Button) and n.is_visible_in_tree():
		if String(n.text).to_lower().contains("win"):
			return true
	for c in n.get_children():
		if _texts_with_win(c):
			return true
	return false


func _score() -> Variant:
	var s := get_tree().current_scene
	return s.get("score") if s else null


func _physics_process(_d: float) -> void:
	_f += 1
	var scene := get_tree().current_scene
	if _phase == 0:
		if _f < 10 or scene == null:
			return
		_player = _find_player(scene)
		if _player == null or not (_player is Node2D or _player is Node3D):
			_r.notes.append("no player node")
			_done()
			return
		_r.player = true
		_start_x = _player.global_position.x
		_r.score_start = _score()
		_r.coins_initial = get_tree().get_nodes_in_group("coins").size()
		Input.action_press("move_right")
		_phase = 1
		_f = 0
	elif _phase == 1:
		if _f < 30:
			return
		Input.action_release("move_right")
		_r.moved = _player.global_position.x - _start_x
		_coins = get_tree().get_nodes_in_group("coins").duplicate()
		_r.coins = _coins.size()
		_r.score_before_pickups = _score()
		_phase = 2
		_f = 0
	elif _phase == 2:
		# Teleport onto each remaining coin in turn and let physics notice the overlap.
		if _f % 12 != 1:
			return
		if _coin_i == 1 and _r.score_after_one == null:
			_r.score_after_one = _score()
		while _coin_i < _coins.size() and not is_instance_valid(_coins[_coin_i]):
			_coin_i += 1
		if _coin_i >= _coins.size():
			_phase = 3
			_f = 0
			return
		if not is_instance_valid(_player):
			_r.notes.append("player vanished")
			_done()
			return
		_player.global_position = _coins[_coin_i].global_position
		_coin_i += 1
	elif _phase == 3:
		if _f < 30:
			return
		_r.score_end = _score()
		if _r.score_after_one == null:
			_r.score_after_one = _r.score_end
		_r.win_text = _texts_with_win(get_tree().root)
		_done()


func _done() -> void:
	print("PROBE_RESULT " + JSON.stringify(_r))
	set_physics_process(false)
	get_tree().quit()
