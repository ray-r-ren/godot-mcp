#!/bin/bash
set -e
set -euo pipefail
mkdir -p /task/inputs /task/truth
python3 /task/make_zip.py /task/star_hop /task/inputs/star_hop.zip star_hop
echo "Star Hop" > /task/truth/game_name.txt
