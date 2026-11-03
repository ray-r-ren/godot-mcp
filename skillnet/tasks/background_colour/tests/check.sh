#!/bin/bash
# Pass when the last hex colour in the answer is within 12 per channel of the running game's background,
# and a PNG screenshot was handed over in /task/outputs.
set -uo pipefail
python3 - <<'PY'
import re, sys
from pathlib import Path
truth = open("/task/truth/background.txt").read().strip().lstrip("#")
tr = [int(truth[i:i + 2], 16) for i in (0, 2, 4)]
try:
    ans = open("/task/answer.txt").read()
except FileNotFoundError:
    print("FAIL: no answer"); sys.exit(1)
hexes = re.findall(r"#([0-9a-fA-F]{6})\b", ans)
if not hexes:
    print("FAIL: no #RRGGBB colour in the answer"); sys.exit(1)
got = hexes[-1]
gr = [int(got[i:i + 2], 16) for i in (0, 2, 4)]
diff = max(abs(a - b) for a, b in zip(gr, tr))
if diff > 12:
    print(f"FAIL: answered #{got}, true background #{truth} (off by {diff})"); sys.exit(1)
outs = Path("/task/outputs")
pngs = [p for p in outs.rglob("*.png")] if outs.exists() else []
if not any(p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in pngs):
    print("FAIL: no screenshot PNG in outputs"); sys.exit(1)
print("PASS", got, "vs", truth)
PY
