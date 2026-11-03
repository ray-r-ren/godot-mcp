#!/bin/bash
set -e
set -euo pipefail
# No inputs: the game is built from the description.
mkdir -p /task/inputs /task/truth
cat > /task/truth/expected.json <<'JSON'
{"timer_name": "Countdown", "start": 60, "ticks_after_2_5s": [2, 3]}
JSON
