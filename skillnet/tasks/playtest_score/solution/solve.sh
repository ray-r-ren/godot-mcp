#!/bin/bash
set -e
# Oracle: run the game headlessly with a small input script (Godot directly, no skill tools) and read the score.
set -euo pipefail
W=$(mktemp -d)
python3 -c "import zipfile; zipfile.ZipFile('/task/inputs/gem_garden.zip').extractall('$W')"
P="$W/gem_garden"
cat > "$P/zz_drive.gd" <<'G'
extends Node
var f := 0
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
func _process(_d: float) -> void:
	f += 1
	if f == 5:
		Input.action_press("move_right")
	elif f == 65:
		Input.action_release("move_right")
		Input.action_press("move_down")
	elif f == 95:
		Input.action_release("move_down")
	elif f == 110:
		print("SCORE=", get_tree().current_scene.score)
		get_tree().quit()
G
printf '\n[autoload]\n\nZZDrive="*res://zz_drive.gd"\n' >> "$P/project.godot"
export HOME=$(mktemp -d)
godot --headless --path "$P" --import >/dev/null 2>&1 || true
S=$(godot --headless --path "$P" --fixed-fps 30 --quit-after 400 2>/dev/null | sed -n 's/^SCORE=//p')
echo "I played it: right for 2 s, then down for 1 s." > /task/answer.txt
echo "Score: $S" >> /task/answer.txt
cat /task/answer.txt
