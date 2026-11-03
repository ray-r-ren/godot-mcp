#!/bin/bash
set -e
# Oracle: check the project with Godot directly (no skill tools) and write the report.
set -euo pipefail
W=$(mktemp -d); cd "$W"; unzip -q /task/inputs/pixel_pond.zip; P="$W/pixel_pond"
export HOME=$(mktemp -d)
godot --headless --path "$P" --import >/dev/null 2>&1 || true
: > /task/answer.txt
for s in $(cd "$P" && find . -name '*.gd' | sed 's|^\./||' | sort); do
  out=$(godot --headless --path "$P" --check-only --script "res://$s" 2>&1 || true)
  line=$(printf '%s\n' "$out" | grep -o "res://$s:[0-9]*" | head -1 | cut -d: -f3 || true)
  msg=$(printf '%s\n' "$out" | grep -m1 'Parse Error' | sed 's/.*Parse Error: //' || true)
  if [ -n "$msg" ]; then echo "ERROR: res://$s line ${line:--} — $msg" >> /task/answer.txt; fi
done
grep -ho 'path="res://[^"]*"' $(find "$P" -name '*.tscn') | sed 's/path="res:\/\///; s/"$//' | sort -u | while read -r f; do
  [ -e "$P/$f" ] || echo "ERROR: res://scenes/main.tscn line - — references res://$f, which does not exist" >> /task/answer.txt
done
cat /task/answer.txt
