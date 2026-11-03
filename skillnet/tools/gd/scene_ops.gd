extends SceneTree
## Batch scene and project-settings editor used by edit_scenes. Runs headless in a throwaway copy
## of the project; stops at the first failing operation. Operations adapted from upstream's
## godot_operations.gd (godot-mcp, MIT): node creation, property conversion, reparenting,
## signals, groups, collision layers, autoloads and project settings.

var _job: Dictionary = {}
var _started := false
var _results: Array = []
var _changed := {}


func _init() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--skillnet-job="):
			_job = JSON.parse_string(FileAccess.get_file_as_string(a.substr("--skillnet-job=".length())))


func _process(_d: float) -> bool:
	if _started:
		return false
	_started = true
	var failed := -1
	var ops: Array = _job.get("operations", [])
	for i in ops.size():
		var op: Dictionary = ops[i]
		var msg = _apply(op)
		var ok: bool = msg is String
		_results.append({"op": op.get("op", ""), "ok": ok, "message": msg if ok else String(msg.get("error", "failed"))})
		if not ok:
			failed = i
			break
	var f := FileAccess.open(_job["result_path"], FileAccess.WRITE)
	f.store_string(JSON.stringify({"results": _results, "failed_op": failed, "scenes_changed": _changed.keys()}))
	f.close()
	quit(0)
	return true


func _err(m: String) -> Dictionary:
	return {"error": m}


func _apply(op: Dictionary):
	match String(op.get("op", "")):
		"create_scene": return _create_scene(op)
		"add_node": return _add_node(op)
		"remove_node": return _remove_node(op)
		"rename_node": return _rename_node(op)
		"reparent_node": return _reparent_node(op)
		"set_properties": return _set_properties(op)
		"attach_script": return _attach_script(op)
		"instantiate_scene": return _instantiate_scene(op)
		"connect_signal": return _connect_signal(op)
		"add_to_group": return _add_to_group(op)
		"set_collision_layers": return _set_collision(op)
		"add_input_action": return _add_input_action(op)
		"set_autoload": return _set_autoload(op)
		"set_main_scene": return _set_main_scene(op)
		"set_setting": return _set_setting(op)
	return _err("unknown operation '%s'" % op.get("op", ""))


# ----------------------------------------------------------------------------- scene helpers

func _open(scene_path: String):
	if not FileAccess.file_exists(scene_path):
		return _err("scene %s does not exist (create it first with create_scene)" % scene_path)
	var ps = ResourceLoader.load(scene_path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if ps == null or not (ps is PackedScene):
		return _err("scene %s could not be loaded" % scene_path)
	var root: Node = ps.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	if root == null:
		return _err("scene %s could not be instantiated" % scene_path)
	return root


func _save(root: Node, scene_path: String):
	var ps := PackedScene.new()
	var e := ps.pack(root)
	if e != OK:
		root.free()
		return _err("packing scene %s failed (error %d)" % [scene_path, e])
	var dir := scene_path.get_base_dir()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(dir))
	e = ResourceSaver.save(ps, scene_path)
	root.free()
	if e != OK:
		return _err("saving scene %s failed (error %d)" % [scene_path, e])
	_changed[scene_path] = true
	return null


func _paths(node: Node, root: Node, out: Array) -> void:
	if out.size() > 40:
		return
	out.append("." if node == root else str(root.get_path_to(node)))
	for c in node.get_children():
		_paths(c, root, out)


func _find(root: Node, path) -> Node:
	var p := String(path if path != null else ".").strip_edges()
	if p.begins_with("root/"):
		p = p.substr(5)
	if p == "" or p == "." or p == "root" or p == String(root.name):
		return root
	if p.begins_with(String(root.name) + "/") and root.get_node_or_null(p) == null:
		p = p.substr(String(root.name).length() + 1)
	return root.get_node_or_null(NodePath(p))


func _missing(root: Node, path) -> Dictionary:
	var all := []
	_paths(root, root, all)
	return _err("node '%s' not found; nodes in this scene: %s" % [path, ", ".join(all)])


func _with_scene(op: Dictionary, fn: Callable):
	var sp := String(op.get("scene", ""))
	var root = _open(sp)
	if root is Dictionary:
		return root
	var r = fn.call(root)
	if r is Dictionary:
		root.free()
		return r
	var s = _save(root, sp)
	if s is Dictionary:
		return s
	return r


# ----------------------------------------------------------------------------- value conversion

func _prop_info(obj: Object, prop: String) -> Dictionary:
	for p in obj.get_property_list():
		if p["name"] == prop:
			return p
	return {}


func _convert(value, info: Dictionary):
	var t: int = info.get("type", TYPE_NIL)
	if value is String and (value.begins_with("Vector") or value.begins_with("Color(") or value.begins_with("Rect2") or value.begins_with("Packed") or value.begins_with("Transform")):
		var v = str_to_var(value)
		if v != null:
			return v
	match t:
		TYPE_BOOL:
			return bool(value)
		TYPE_INT:
			if value is float or value is int or value is bool:
				return int(value)
		TYPE_FLOAT:
			if value is float or value is int:
				return float(value)
		TYPE_STRING:
			return str(value)
		TYPE_STRING_NAME:
			return StringName(str(value))
		TYPE_NODE_PATH:
			return NodePath(str(value))
		TYPE_VECTOR2:
			if value is Array and value.size() == 2: return Vector2(value[0], value[1])
			if value is Dictionary: return Vector2(value.get("x", 0), value.get("y", 0))
		TYPE_VECTOR2I:
			if value is Array and value.size() == 2: return Vector2i(int(value[0]), int(value[1]))
		TYPE_VECTOR3:
			if value is Array and value.size() == 3: return Vector3(value[0], value[1], value[2])
			if value is Dictionary: return Vector3(value.get("x", 0), value.get("y", 0), value.get("z", 0))
		TYPE_VECTOR3I:
			if value is Array and value.size() == 3: return Vector3i(int(value[0]), int(value[1]), int(value[2]))
		TYPE_RECT2:
			if value is Array and value.size() == 4: return Rect2(value[0], value[1], value[2], value[3])
		TYPE_COLOR:
			if value is Array and value.size() == 3: return Color(value[0], value[1], value[2])
			if value is Array and value.size() == 4: return Color(value[0], value[1], value[2], value[3])
			if value is String:
				var c1 := Color.from_string(value, Color(0, 0, 0, 0))
				var c2 := Color.from_string(value, Color(1, 1, 1, 0.5))
				if c1 != c2:
					return _err("'%s' is not a colour (use [r, g, b], '#rrggbb' or a name like 'red')" % value)
				return c1
			if value is Dictionary: return Color(value.get("r", 0), value.get("g", 0), value.get("b", 0), value.get("a", 1))
		TYPE_PACKED_VECTOR2_ARRAY:
			if value is Array:
				var arr := PackedVector2Array()
				for p in value:
					arr.append(Vector2(p[0], p[1]))
				return arr
		TYPE_PACKED_STRING_ARRAY:
			if value is Array: return PackedStringArray(value)
		TYPE_OBJECT:
			if value == null:
				return null
			if value is String and value.begins_with("res://"):
				if not ResourceLoader.exists(value):
					return _err("resource %s does not exist" % value)
				return load(value)
			if value is Dictionary and value.has("type"):
				return _make_object(value)
	return value


func _make_object(spec: Dictionary):
	var cls := String(spec["type"])
	if not ClassDB.class_exists(cls) or not ClassDB.can_instantiate(cls):
		return _err("'%s' is not a Godot class that can be created" % cls)
	if not ClassDB.is_parent_class(cls, "Resource"):
		return _err("'%s' is not a resource type (use add_node for nodes)" % cls)
	var obj: Resource = ClassDB.instantiate(cls)
	for k in spec:
		if k == "type":
			continue
		var r = _set_one(obj, k, spec[k])
		if r is Dictionary:
			return r
	return obj


func _set_one(obj: Object, prop: String, value):
	var info := _prop_info(obj, prop)
	if info.is_empty() and not prop.begins_with("metadata/"):
		var cls: String = obj.get_class()
		return _err("%s has no property '%s'" % [cls, prop])
	var v = _convert(value, info)
	if v is Dictionary and v.has("error") and info.get("type", TYPE_NIL) != TYPE_DICTIONARY:
		return v
	obj.set(prop, v)
	return null


func _set_props(node: Object, props) -> Variant:
	if props == null:
		return null
	if not (props is Dictionary):
		return _err("properties must be an object of name: value")
	for k in props:
		var r = _set_one(node, String(k), props[k])
		if r is Dictionary:
			return _err("node '%s': %s" % [node.name if node is Node else "", r["error"]])
	return null


func _load_script(path: String):
	if not FileAccess.file_exists(path):
		return _err("script %s does not exist (write it first with write_game_files)" % path)
	var s = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if s == null or not (s is Script):
		return _err("script %s could not be loaded (fix its errors with write_game_files)" % path)
	return s


# ----------------------------------------------------------------------------- scene operations

func _create_scene(op: Dictionary):
	var sp := String(op.get("scene", ""))
	if FileAccess.file_exists(sp):
		return _err("scene %s already exists" % sp)
	var t := String(op.get("type", "Node2D"))
	if not ClassDB.class_exists(t) or not ClassDB.is_parent_class(t, "Node") or not ClassDB.can_instantiate(t):
		return _err("'%s' is not a Godot node type" % t)
	var root: Node = ClassDB.instantiate(t)
	root.name = String(op.get("name", sp.get_file().get_basename().to_pascal_case()))
	if op.get("script"):
		var s = _load_script(String(op["script"]))
		if s is Dictionary:
			root.free()
			return s
		root.set_script(s)
	var r = _set_props(root, op.get("properties"))
	if r is Dictionary:
		root.free()
		return r
	var sv = _save(root, sp)
	if sv is Dictionary:
		return sv
	return "created %s with root %s (%s)" % [sp, op.get("name", sp.get_file().get_basename().to_pascal_case()), t]


func _add_node(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var parent := _find(root, op.get("parent", "."))
		if parent == null:
			return _missing(root, op.get("parent"))
		var t := String(op.get("type", ""))
		if not ClassDB.class_exists(t) or not ClassDB.is_parent_class(t, "Node") or not ClassDB.can_instantiate(t):
			return _err("'%s' is not a Godot node type (examples: Sprite2D, CharacterBody2D, Area2D, CollisionShape2D, Label, Timer)" % t)
		var name := String(op.get("name", t))
		if parent.has_node(NodePath(name)):
			return _err("'%s' already has a child named '%s'" % [op.get("parent", "."), name])
		var node: Node = ClassDB.instantiate(t)
		node.name = name
		if op.get("script"):
			var s = _load_script(String(op["script"]))
			if s is Dictionary:
				node.free()
				return s
			node.set_script(s)
		var r = _set_props(node, op.get("properties"))
		if r is Dictionary:
			node.free()
			return r
		parent.add_child(node)
		node.owner = root
		for g in op.get("groups", []):
			node.add_to_group(String(g), true)
		return "added %s '%s' under '%s'" % [t, name, op.get("parent", ".")])


func _remove_node(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var node := _find(root, op.get("node"))
		if node == null:
			return _missing(root, op.get("node"))
		if node == root:
			return _err("cannot remove the scene's root node")
		node.get_parent().remove_child(node)
		node.free()
		return "removed '%s'" % op.get("node"))


func _rename_node(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var node := _find(root, op.get("node"))
		if node == null:
			return _missing(root, op.get("node"))
		var old := String(node.name)
		node.name = String(op.get("name", old))
		return "renamed '%s' to '%s'" % [old, node.name])


func _reparent_node(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var node := _find(root, op.get("node"))
		if node == null:
			return _missing(root, op.get("node"))
		var parent := _find(root, op.get("parent", "."))
		if parent == null:
			return _missing(root, op.get("parent"))
		if node == root or node.is_ancestor_of(parent) or node == parent:
			return _err("cannot move '%s' under itself or move the root" % op.get("node"))
		var keep: bool = op.get("keep_global_transform", false)
		node.reparent(parent, keep)
		if node.owner == null:
			node.owner = root
		return "moved '%s' under '%s'" % [node.name, op.get("parent", ".")])


func _set_properties(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var node := _find(root, op.get("node", "."))
		if node == null:
			return _missing(root, op.get("node"))
		var r = _set_props(node, op.get("properties", {}))
		if r is Dictionary:
			return r
		return "set %s on '%s'" % [", ".join(PackedStringArray(op.get("properties", {}).keys())), op.get("node", ".")])


func _attach_script(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var node := _find(root, op.get("node", "."))
		if node == null:
			return _missing(root, op.get("node"))
		var s = _load_script(String(op.get("script", "")))
		if s is Dictionary:
			return s
		var base := String(s.get_instance_base_type())
		if not node.is_class(base):
			return _err("script %s extends %s but node '%s' is a %s" % [op.get("script"), base, op.get("node", "."), node.get_class()])
		node.set_script(s)
		return "attached %s to '%s'" % [op.get("script"), op.get("node", ".")])


func _instantiate_scene(op: Dictionary):
	var child_path := String(op.get("child_scene", ""))
	if child_path == String(op.get("scene", "")):
		return _err("a scene cannot contain itself")
	return _with_scene(op, func(root: Node):
		var parent := _find(root, op.get("parent", "."))
		if parent == null:
			return _missing(root, op.get("parent"))
		if not FileAccess.file_exists(child_path):
			return _err("scene %s does not exist" % child_path)
		var ps = ResourceLoader.load(child_path, "", ResourceLoader.CACHE_MODE_IGNORE)
		if ps == null or not (ps is PackedScene):
			return _err("scene %s could not be loaded" % child_path)
		var inst: Node = ps.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
		if op.get("name"):
			inst.name = String(op["name"])
		if parent.has_node(NodePath(String(inst.name))):
			var n := String(inst.name)
			inst.free()
			return _err("'%s' already has a child named '%s' (give a different name)" % [op.get("parent", "."), n])
		var r = _set_props(inst, op.get("properties"))
		if r is Dictionary:
			inst.free()
			return r
		parent.add_child(inst)
		inst.owner = root
		for g in op.get("groups", []):
			inst.add_to_group(String(g), true)
		return "instanced %s as '%s' under '%s'" % [child_path, inst.name, op.get("parent", ".")])


func _connect_signal(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var src := _find(root, op.get("node", "."))
		if src == null:
			return _missing(root, op.get("node"))
		var tgt := _find(root, op.get("target", "."))
		if tgt == null:
			return _missing(root, op.get("target"))
		var sig := String(op.get("signal", ""))
		if not src.has_signal(sig):
			var names := []
			for s in src.get_signal_list():
				names.append(s["name"])
			return _err("%s '%s' has no signal '%s'; it has: %s" % [src.get_class(), op.get("node", "."), sig, ", ".join(names.slice(0, 30))])
		var method := String(op.get("method", ""))
		var c := Callable(tgt, method)
		if src.is_connected(sig, c):
			return "already connected %s.%s -> %s.%s" % [src.name, sig, tgt.name, method]
		src.connect(sig, c, CONNECT_PERSIST)
		var note := "" if tgt.has_method(method) else " (note: '%s' has no method '%s' yet; add it to its script)" % [tgt.name, method]
		return "connected %s.%s -> %s.%s%s" % [src.name, sig, tgt.name, method, note])


func _add_to_group(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var node := _find(root, op.get("node", "."))
		if node == null:
			return _missing(root, op.get("node"))
		for g in op.get("groups", []):
			node.add_to_group(String(g), true)
		return "added '%s' to groups %s" % [op.get("node", "."), ", ".join(PackedStringArray(op.get("groups", [])))])


func _bits(v) -> int:
	if v is Array:
		var out := 0
		for b in v:
			out |= 1 << (int(b) - 1)
		return out
	return int(v)


func _set_collision(op: Dictionary):
	return _with_scene(op, func(root: Node):
		var node := _find(root, op.get("node", "."))
		if node == null:
			return _missing(root, op.get("node"))
		if not ("collision_layer" in node):
			return _err("'%s' (%s) has no collision layers; use a physics body, Area or TileMapLayer" % [op.get("node"), node.get_class()])
		if op.has("layers") and op["layers"] != null:
			node.collision_layer = _bits(op["layers"])
		if op.has("mask") and op["mask"] != null:
			node.collision_mask = _bits(op["mask"])
		return "'%s' collision_layer=%d collision_mask=%d" % [op.get("node"), node.collision_layer, node.collision_mask])


# ----------------------------------------------------------------------------- project operations

func _save_settings(what: String):
	var e := ProjectSettings.save()
	if e != OK:
		return _err("saving project.godot failed (error %d)" % e)
	_changed["res://project.godot"] = true
	return what


func _add_input_action(op: Dictionary):
	var name := String(op.get("name", ""))
	var events := []
	for k in op.get("keys", []):
		var key := String(k)
		var low := key.to_lower()
		if low.begins_with("mouse_"):
			var mb := {"mouse_left": MOUSE_BUTTON_LEFT, "mouse_right": MOUSE_BUTTON_RIGHT, "mouse_middle": MOUSE_BUTTON_MIDDLE,
				"mouse_wheel_up": MOUSE_BUTTON_WHEEL_UP, "mouse_wheel_down": MOUSE_BUTTON_WHEEL_DOWN}
			if not mb.has(low):
				return _err("unknown mouse button '%s' (use mouse_left, mouse_right, mouse_middle, mouse_wheel_up, mouse_wheel_down)" % key)
			var me := InputEventMouseButton.new()
			me.button_index = mb[low]
			events.append(me)
			continue
		var code := OS.find_keycode_from_string(key)
		if code == KEY_NONE:
			return _err("unknown key name '%s' (use names like A, Space, Enter, Escape, Left, Right, Up, Down, Shift)" % key)
		var ev := InputEventKey.new()
		ev.physical_keycode = code
		events.append(ev)
	ProjectSettings.set_setting("input/" + name, {"deadzone": float(op.get("deadzone", 0.2)), "events": events})
	return _save_settings("input action '%s' = %s" % [name, ", ".join(PackedStringArray(op.get("keys", [])))])


func _set_autoload(op: Dictionary):
	var name := String(op.get("name", ""))
	if op.get("remove", false):
		if not ProjectSettings.has_setting("autoload/" + name):
			return _err("there is no autoload named '%s'" % name)
		ProjectSettings.set_setting("autoload/" + name, null)
		return _save_settings("removed autoload '%s'" % name)
	var path := String(op.get("script", ""))
	if not FileAccess.file_exists(path):
		return _err("%s does not exist (write it first with write_game_files)" % path)
	ProjectSettings.set_setting("autoload/" + name, "*" + path)
	return _save_settings("autoload '%s' = %s" % [name, path])


func _set_main_scene(op: Dictionary):
	var sp := String(op.get("scene", ""))
	if not FileAccess.file_exists(sp):
		return _err("scene %s does not exist" % sp)
	ProjectSettings.set_setting("application/run/main_scene", sp)
	return _save_settings("main scene = %s" % sp)


func _set_setting(op: Dictionary):
	var key := String(op.get("setting", ""))
	var value = op.get("value")
	if ProjectSettings.has_setting(key):
		var cur = ProjectSettings.get_setting(key)
		var info := {"type": typeof(cur)}
		value = _convert(value, info)
	ProjectSettings.set_setting(key, value)
	return _save_settings("%s = %s" % [key, str(value)])
