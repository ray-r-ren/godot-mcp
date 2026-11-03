extends Node
## Injected (temporarily, into a throwaway copy) by playtest_game: plays a scripted sequence of
## inputs, waits, screenshots, expressions and assertions inside the running game, frame by frame
## at a fixed frame rate. Input injection and expression evaluation adapted from upstream's
## input_receiver.gd (godot-mcp, MIT); runs the whole sequence in-process instead of over TCP.

var _cfg: Dictionary = {}
var _fps: float = 30.0
var _out: FileAccess


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var path := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--skillnet-playtest="):
			path = a.substr("--skillnet-playtest=".length())
	if path.is_empty() or not FileAccess.file_exists(path):
		printerr("[SKN] playtest config missing")
		return
	_cfg = JSON.parse_string(FileAccess.get_file_as_string(path))
	_fps = float(_cfg.get("fps", 30))
	_out = FileAccess.open(_cfg["results_path"], FileAccess.WRITE)
	print("[SKN-PLAY] started")
	_run.call_deferred()


func _emit(d: Dictionary) -> void:
	_out.store_line(JSON.stringify(d))
	_out.flush()


func _frames(n: int) -> void:
	for i in maxi(0, n):
		await get_tree().process_frame


func _run() -> void:
	await _frames(int(_cfg.get("warmup_frames", 3)))
	var steps: Array = _cfg.get("steps", [])
	for i in steps.size():
		printerr("[SKN-STEP] %d" % i)
		print("[SKN-STEP] %d" % i)
		var r: Dictionary = await _do_step(steps[i])
		r["index"] = i
		r["frame"] = Engine.get_process_frames()
		_emit(r)
	printerr("[SKN-STEP] -1")
	_emit({"type": "end"})
	_out.close()
	print("[SKN-PLAY] finished")
	get_tree().quit(0)


func _do_step(s: Dictionary) -> Dictionary:
	match String(s.get("kind", "")):
		"action":
			return await _step_action(s)
		"key":
			return await _step_key(s)
		"click":
			return await _step_click(s)
		"wait":
			await _frames(int(s.get("frames", 1)))
			return {"ok": true}
		"screenshot":
			return await _step_screenshot(s)
		"eval":
			var e := _evaluate(String(s.get("expr", "")))
			if e.has("error"):
				return {"ok": false, "error": e["error"]}
			return {"ok": true, "value": _ser(e["value"])}
		"assert":
			var a := _evaluate(String(s.get("expr", "")))
			if a.has("error"):
				return {"ok": false, "passed": false, "error": a["error"]}
			var passed := true if a["value"] else false
			return {"ok": passed, "passed": passed, "value": _ser(a["value"])}
		"wait_until":
			var limit := int(s.get("timeout_frames", 150))
			for f in limit:
				var w := _evaluate(String(s.get("expr", "")))
				if w.has("error"):
					return {"ok": false, "error": w["error"]}
				if w["value"]:
					return {"ok": true, "value": _ser(w["value"]), "waited_frames": f}
				await get_tree().process_frame
			return {"ok": false, "error": "condition still false after %d frames" % limit}
	return {"ok": false, "error": "unknown step"}


func _step_action(s: Dictionary) -> Dictionary:
	var name := String(s.get("action", ""))
	if not InputMap.has_action(name):
		var known := []
		for a in InputMap.get_actions():
			if not String(a).begins_with("ui_"):
				known.append(String(a))
		return {"ok": false, "error": "unknown input action '%s'; the project defines: %s" % [name, ", ".join(known)]}
	var ev := InputEventAction.new()
	ev.action = name
	ev.pressed = true
	ev.strength = 1.0
	Input.parse_input_event(ev)
	await _frames(int(s.get("hold_frames", 3)))
	var up := InputEventAction.new()
	up.action = name
	up.pressed = false
	Input.parse_input_event(up)
	await _frames(1)
	return {"ok": true}


func _step_key(s: Dictionary) -> Dictionary:
	var key := String(s.get("key", ""))
	var code := OS.find_keycode_from_string(key)
	if code == KEY_NONE:
		return {"ok": false, "error": "unknown key name '%s' (use names like A, Space, Enter, Escape, Left, Up, Shift)" % key}
	var ev := InputEventKey.new()
	ev.keycode = code
	ev.physical_keycode = code
	ev.pressed = true
	if key.length() == 1:
		ev.unicode = key.to_lower().unicode_at(0)
	Input.parse_input_event(ev)
	await _frames(int(s.get("hold_frames", 3)))
	var up := ev.duplicate()
	up.pressed = false
	Input.parse_input_event(up)
	await _frames(1)
	return {"ok": true}


func _step_click(s: Dictionary) -> Dictionary:
	var pos := Vector2(float(s.get("x", 0)), float(s.get("y", 0)))
	var buttons := {"left": MOUSE_BUTTON_LEFT, "right": MOUSE_BUTTON_RIGHT, "middle": MOUSE_BUTTON_MIDDLE}
	var b: int = buttons.get(String(s.get("button", "left")), MOUSE_BUTTON_LEFT)
	var mv := InputEventMouseMotion.new()
	mv.position = pos
	mv.global_position = pos
	Input.parse_input_event(mv)
	await _frames(1)
	var ev := InputEventMouseButton.new()
	ev.position = pos
	ev.global_position = pos
	ev.button_index = b
	ev.pressed = true
	Input.parse_input_event(ev)
	await _frames(int(s.get("hold_frames", 2)))
	var up := ev.duplicate()
	up.pressed = false
	Input.parse_input_event(up)
	await _frames(1)
	return {"ok": true}


func _step_screenshot(s: Dictionary) -> Dictionary:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	if img == null:
		return {"ok": false, "error": "could not read the viewport image"}
	var out: String = String(_cfg["out_dir"]).path_join(String(s.get("name", "shot")) + ".png")
	var err := img.save_png(out)
	if err != OK:
		return {"ok": false, "error": "could not save the screenshot (error %d)" % err}
	return {"ok": true, "file": out.get_file()}


func _evaluate(expr_str: String) -> Dictionary:
	if expr_str.strip_edges().is_empty():
		return {"error": "empty expression"}
	var names := PackedStringArray()
	var values: Array = []
	var scene := get_tree().current_scene
	for child in get_tree().root.get_children():
		if child == scene or String(child.name).begins_with("_"):
			continue
		names.append(String(child.name))
		values.append(child)
	# Engine singletons are not visible to Expression when a base instance is set; pass the useful ones in.
	for single in ["Input", "Engine", "InputMap", "ProjectSettings"]:
		if not names.has(single):
			names.append(single)
			values.append(Engine.get_singleton(single))
	var expression := Expression.new()
	if expression.parse(expr_str, names) != OK:
		return {"error": "parse error: " + expression.get_error_text()}
	var base: Object = scene if scene else self
	var result = expression.execute(values, base, false)
	if expression.has_execute_failed():
		return {"error": "evaluation failed: " + expression.get_error_text()}
	return {"value": result}


func _ser(value: Variant) -> Variant:
	if value == null:
		return null
	if value is bool or value is int or value is String:
		return value
	if value is float:
		return snappedf(value, 0.0001)
	if value is StringName or value is NodePath:
		return String(value)
	if value is Vector2 or value is Vector2i:
		return [snappedf(value.x, 0.001), snappedf(value.y, 0.001)]
	if value is Vector3 or value is Vector3i:
		return [snappedf(value.x, 0.001), snappedf(value.y, 0.001), snappedf(value.z, 0.001)]
	if value is Color:
		return "#" + value.to_html(true)
	if value is Array:
		var arr: Array = []
		for item in value.slice(0, 50):
			arr.append(_ser(item))
		return arr
	if value is Dictionary:
		var d := {}
		var n := 0
		for k in value:
			if n >= 50:
				break
			d[str(k)] = _ser(value[k])
			n += 1
		return d
	if value is Node:
		return {"node": String(value.name), "class": value.get_class(), "path": str(value.get_path())}
	if value is Resource:
		return {"resource": value.get_class(), "path": value.resource_path}
	return str(value)
