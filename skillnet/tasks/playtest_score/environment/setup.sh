#!/bin/bash
set -e
set -euo pipefail
mkdir -p /task/inputs /task/truth
python3 /task/make_zip.py /task/gem_garden /task/inputs/gem_garden.zip gem_garden
# Right 2 s at 250 px/s from (100, 300) reaches x = 600: gems 5 + 2 (the 5 at x = 690 is out of reach).
# Down 1 s reaches y = 550: the 2 at (600, 450) is in the lower meadow and counts double (4); the 10 at y = 620 is out of reach.
echo 11 > /task/truth/score.txt
