extends Node
## Injected (temporarily, into a throwaway copy) by run_game: takes screenshots at chosen
## game-time moments and quits after the requested duration. Adapted from upstream's
## run_and_capture.gd (godot-mcp, MIT).

var _cfg: Dictionary = {}
var _shots: Array = []
var _fps: float = 30.0
var _end_frame: int = 0
var _frame: int = 0
var _taken: Array = []
var _done := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	process_priority = 1000000
	var path := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--skillnet-run="):
			path = a.substr("--skillnet-run=".length())
	if path.is_empty() or not FileAccess.file_exists(path):
		printerr("[SKN] run config missing")
		return
	_cfg = JSON.parse_string(FileAccess.get_file_as_string(path))
	_fps = float(_cfg.get("fps", 30))
	_end_frame = maxi(1, int(round(float(_cfg.get("seconds", 5.0)) * _fps)))
	for t in _cfg.get("screenshot_at", []):
		_shots.append(clampi(int(round(float(t) * _fps)), 1, _end_frame))
	print("[SKN-RUN] started")


func _process(_delta: float) -> void:
	if _cfg.is_empty() or _done:
		return
	_frame += 1
	var want := []
	for i in _shots.size():
		if _shots[i] == _frame:
			want.append(i)
	if _frame % 15 == 0:
		print("[SKN-RUN] frame %d" % _frame)
	if not want.is_empty():
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		for i in want:
			var out: String = _cfg["out_dir"].path_join("shot_%02d.png" % i)
			if img:
				img.save_png(out)
				_taken.append({"index": i, "frame": _frame, "path": out})
	if _frame >= _end_frame and not _done:
		_done = true
		_finish()


func _finish() -> void:
	var info := {"frames": _frame, "shots": _taken, "ended": true,
		"scene": str(get_tree().current_scene.scene_file_path) if get_tree().current_scene else ""}
	var f := FileAccess.open(_cfg["info_path"], FileAccess.WRITE)
	f.store_string(JSON.stringify(info))
	f.close()
	print("[SKN-RUN] finished")
	get_tree().quit(0)
