#!/bin/bash
set -e
set -euo pipefail
mkdir -p /task/inputs /task/truth
python3 /task/make_zip.py /task/night_pond /task/inputs/night_pond.zip night_pond
# main.gd sets the sky at start-up to Color.from_hsv(0.6, 0.7, 0.5) = (0.15, 0.29, 0.5) -> #264a80.
# (The scene file's green and the project's grey clear colour are never what the running game shows.)
echo "#264a80" > /task/truth/background.txt
