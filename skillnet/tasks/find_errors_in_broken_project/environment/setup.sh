#!/bin/bash
set -e
set -euo pipefail
mkdir -p /task/inputs /task/truth
python3 /task/make_zip.py /task/pixel_pond /task/inputs/pixel_pond.zip pixel_pond
# Two real problems: a missing ':' after the if on line 9 of player.gd, and a scene pointing at a script that doesn't exist.
cat > /task/truth/expected.json <<'JSON'
{"parse_file": "player.gd", "parse_line": 9, "missing_file": "frog_ai.gd"}
JSON
