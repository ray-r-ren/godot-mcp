extends SceneTree
## Headless project checker used by check_project and write_game_files: compiles scripts and
## loads/instantiates scenes, verifying signal connections. Engine errors go to stderr (parsed by
## the tool for file and line); structured findings go to the result JSON.

var _job: Dictionary = {}
var _started := false


func _init() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--skillnet-job="):
			_job = JSON.parse_string(FileAccess.get_file_as_string(a.substr("--skillnet-job=".length())))


func _process(_d: float) -> bool:
	if _started:
		return false
	_started = true
	var result := {"scripts": [], "scenes": []}
	for p in _job.get("scripts", []):
		printerr("[SKN-FILE] " + p)
		var s = ResourceLoader.load(p, "", ResourceLoader.CACHE_MODE_IGNORE)
		var ok: bool = s != null and s is Script and s.can_instantiate()
		var entry := {"path": p, "ok": ok}
		if s is GDScript and ok:
			entry["base"] = str(s.get_instance_base_type())
		result["scripts"].append(entry)
	for p in _job.get("scenes", []):
		printerr("[SKN-FILE] " + p)
		result["scenes"].append(_check_scene(p))
	var f := FileAccess.open(_job["result_path"], FileAccess.WRITE)
	f.store_string(JSON.stringify(result))
	f.close()
	quit(0)
	return true


const GODOT3_TYPES := {
	"KinematicBody2D": "CharacterBody2D", "KinematicBody": "CharacterBody3D", "Spatial": "Node3D",
	"Sprite": "Sprite2D", "Position2D": "Marker2D", "Position3D": "Marker3D", "Particles2D": "GPUParticles2D",
	"Particles": "GPUParticles3D", "YSort": "Node2D with y_sort_enabled", "Tween": "create_tween() in code",
	"RigidBody": "RigidBody3D", "StaticBody": "StaticBody3D", "Area": "Area3D", "CollisionShape": "CollisionShape3D",
	"MeshInstance": "MeshInstance3D", "Camera": "Camera3D", "DirectionalLight": "DirectionalLight3D",
	"OmniLight": "OmniLight3D", "SpotLight": "SpotLight3D", "VisibilityNotifier2D": "VisibleOnScreenNotifier2D",
	"ToolButton": "Button with flat = true", "Navigation2D": "NavigationRegion2D", "Light2D": "PointLight2D",
	"AnimatedSprite": "AnimatedSprite2D", "RayCast": "RayCast3D", "CSGBox": "CSGBox3D",
}
var _global_classes := {}


func _check_scene(p: String) -> Dictionary:
	if _global_classes.is_empty():
		for g in ProjectSettings.get_global_class_list():
			_global_classes[str(g.get("class", ""))] = true
	var entry := {"path": p, "ok": true, "problems": []}
	var ps = ResourceLoader.load(p, "", ResourceLoader.CACHE_MODE_IGNORE)
	if ps == null or not (ps is PackedScene):
		entry["ok"] = false
		entry["problems"].append("the scene could not be loaded")
		return entry
	var st: SceneState = ps.get_state()
	entry["nodes"] = st.get_node_count()
	if st.get_node_count() > 0:
		entry["root_type"] = str(st.get_node_type(0))
	for i in st.get_node_count():
		var t := str(st.get_node_type(i))
		if t != "" and not ClassDB.class_exists(t) and not _global_classes.has(t):
			entry["ok"] = false
			var hint := ""
			if GODOT3_TYPES.has(t):
				hint = " (Godot 3 name; in Godot 4 use %s)" % GODOT3_TYPES[t]
			entry["problems"].append("node '%s' has unknown type '%s'%s" % [str(st.get_node_path(i)), t, hint])
	if not ps.can_instantiate():
		entry["ok"] = false
		entry["problems"].append("the scene cannot be instantiated")
		return entry
	var inst: Node = ps.instantiate()
	if inst == null:
		entry["ok"] = false
		entry["problems"].append("instantiating the scene failed")
		return entry
	for i in st.get_node_count():
		var np := st.get_node_path(i)
		var n := inst.get_node_or_null(np)
		if n == null:
			continue
		for k in st.get_node_property_count(i):
			if str(st.get_node_property_name(i, k)) == "script":
				var sc = st.get_node_property_value(i, k)
				if sc == null or (sc is Script and not sc.can_instantiate()):
					entry["ok"] = false
					entry["problems"].append("node '%s' has a script that failed to load" % str(np))
	for c in st.get_connection_count():
		var src := st.get_connection_source(c)
		var tgt := st.get_connection_target(c)
		var sig := str(st.get_connection_signal(c))
		var method := str(st.get_connection_method(c))
		var sn := inst.get_node_or_null(src)
		var tn := inst.get_node_or_null(tgt)
		if sn == null:
			entry["ok"] = false
			entry["problems"].append("connection '%s': source node '%s' does not exist" % [sig, str(src)])
			continue
		if tn == null:
			entry["ok"] = false
			entry["problems"].append("connection '%s': target node '%s' does not exist" % [sig, str(tgt)])
			continue
		if not sn.has_signal(sig):
			entry["ok"] = false
			entry["problems"].append("connection: node '%s' has no signal '%s'" % [str(src), sig])
		if not tn.has_method(method):
			entry["ok"] = false
			entry["problems"].append("connection '%s': node '%s' has no method '%s'" % [sig, str(tgt), method])
	inst.free()
	return entry
