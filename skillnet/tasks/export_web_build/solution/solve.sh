#!/bin/bash
set -e
# Oracle: export with Godot directly (no skill tools) using the installed web templates.
set -euo pipefail
W=$(mktemp -d)
python3 -c "import zipfile; zipfile.ZipFile('/task/inputs/star_hop.zip').extractall('$W')"
P="$W/star_hop"
cat > "$P/export_presets.cfg" <<'C'
[preset.0]

name="Web"
platform="Web"
runnable=true
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path=""

[preset.0.options]

variant/extensions_support=false
variant/thread_support=false
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/export_icon=true
html/canvas_resize_policy=2
progressive_web_app/enabled=false
C
export HOME=$(mktemp -d)
export XDG_DATA_HOME=/opt/godot-data
mkdir -p "$W/build"
godot --headless --path "$P" --import >/dev/null 2>&1 || true
godot --headless --path "$P" --export-release "Web" "$W/build/index.html" >/dev/null 2>&1
mkdir -p /task/outputs
python3 - "$W/build" /task/outputs/star_hop_web.zip <<'PY'
import sys, zipfile
from pathlib import Path
src, dest = Path(sys.argv[1]), sys.argv[2]
with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in sorted(src.iterdir()):
        zf.write(p, p.name)
PY
echo "Web build of Star Hop: index.html (the page), index.js (engine loader), index.wasm (engine), index.pck (game data)." > /task/answer.txt
