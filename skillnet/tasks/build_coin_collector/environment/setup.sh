#!/bin/bash
set -e
# No inputs: the game is built from the description. The truth holds the required numbers.
set -euo pipefail
mkdir -p /task/inputs /task/truth
cat > /task/truth/expected.json <<'JSON'
{"min_coins": 5, "score_per_coin": 1, "min_move_px": 20}
JSON
