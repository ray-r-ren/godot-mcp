extends Node
## Independent checker injected as an autoload: inspects the Countdown timer, its signal and time_left over 2.5 s.

var _f := 0
var _r := {"timer": false, "wait_time": null, "connections": 0, "connected_to_main": false, "time_left_start": null,
		"time_left_end": null, "jump_action": false, "player_body": false, "label_shows_time": false}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


func _bodies(n: Node) -> bool:
	if n is CharacterBody2D or n is CharacterBody3D:
		return true
	for c in n.get_children():
		if _bodies(c):
			return true
	return false


func _labels_with(n: Node, needle: String) -> bool:
	if (n is Label or n is RichTextLabel) and n.is_visible_in_tree() and String(n.text).contains(needle):
		return true
	for c in n.get_children():
		if _labels_with(c, needle):
			return true
	return false


func _physics_process(_d: float) -> void:
	_f += 1
	var scene := get_tree().current_scene
	if scene == null:
		if _f > 120:
			_done()
		return
	if _f == 6:
		var t := scene.get_node_or_null("Countdown")
		if t == null:
			t = scene.find_child("Countdown", true, false)
		if t is Timer:
			_r.timer = true
			_r.wait_time = t.wait_time
			var conns: Array = t.get_signal_connection_list("timeout")
			_r.connections = conns.size()
			for c in conns:
				if c["callable"].get_object() == scene:
					_r.connected_to_main = true
		_r.time_left_start = scene.get("time_left")
		_r.jump_action = InputMap.has_action("jump") or InputMap.has_action("ui_accept")
		_r.player_body = _bodies(scene)
	elif _f == 6 + 150:
		_r.time_left_end = scene.get("time_left")
		if _r.time_left_end != null:
			_r.label_shows_time = _labels_with(scene, str(_r.time_left_end))
		_done()


func _done() -> void:
	print("PROBE_RESULT ", JSON.stringify(_r))
	get_tree().quit()
