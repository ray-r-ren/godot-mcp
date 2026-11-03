#!/bin/bash
set -e
set -euo pipefail
mkdir -p /task/inputs /task/truth
python3 /task/make_zip.py /task/meadow_dash /task/inputs/meadow_dash.zip meadow_dash
# Two coins worth 1 and 3: touching both must add 4.
cat > /task/truth/expected.json <<'JSON'
{"coins": 2, "score_gain": 4, "min_move_px": 20}
JSON
