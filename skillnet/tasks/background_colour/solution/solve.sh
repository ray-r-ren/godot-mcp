#!/bin/bash
set -e
# Oracle: run the game with Godot directly in a virtual display (no skill tools), grab a frame
# after one second, and read the most common pixel colour.
set -euo pipefail
W=$(mktemp -d)
python3 -c "import zipfile; zipfile.ZipFile('/task/inputs/night_pond.zip').extractall('$W')"
P="$W/night_pond"
mkdir -p /task/outputs
cat > "$P/zz_shot.gd" <<'G'
extends Node
var f := 0
func _process(_d: float) -> void:
	f += 1
	if f == 30:
		get_viewport().get_texture().get_image().save_png("/task/outputs/night_pond.png")
		get_tree().quit()
G
printf '\n[autoload]\n\nZZShot="*res://zz_shot.gd"\n' >> "$P/project.godot"
export HOME=$(mktemp -d)
godot --headless --path "$P" --import >/dev/null 2>&1 || true
xvfb-run -a -s "-screen 0 1280x720x24" godot --rendering-driver opengl3 --path "$P" --fixed-fps 30 --quit-after 300 >/dev/null 2>&1 || true
HEX=$(python3 -c "
from PIL import Image
im = Image.open('/task/outputs/night_pond.png').convert('RGB')
c = max(im.getcolors(im.width * im.height), key=lambda c: c[0])[1]
print('#%02x%02x%02x' % c)")
printf 'I ran the game and sampled the screenshot.\nBackground: %s\n' "$HEX" > /task/answer.txt
cat /task/answer.txt
