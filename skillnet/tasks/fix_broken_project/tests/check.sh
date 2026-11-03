#!/bin/bash
# Independent check: the fixed project runs headlessly with no engine errors, moves on move_right,
# and touching both coins adds 1 + 3 to `score`.
set -uo pipefail
export PROBE_OUT=/tmp/probe_out.json
rm -f "$PROBE_OUT"
python3 /task/run_probe.py /task/outputs || { echo "FAIL: no runnable project found"; exit 1; }
python3 - <<'PY'
import json, sys
o = json.load(open("/tmp/probe_out.json"))
t = json.load(open("/task/truth/expected.json"))
r = o["result"]
fails = []
if o["errors"]:
    fails.append("engine errors remain: " + " | ".join(o["errors"][:3]))
if r is None:
    fails.append("the game did not run to the end of the probe")
else:
    if r["moved"] < t["min_move_px"]:
        fails.append(f"move_right moved the player only {r['moved']} px")
    if r["coins_initial"] != t["coins"]:
        fails.append(f"expected {t['coins']} coins, found {r['coins_initial']}")
    if not isinstance(r["score_start"], (int, float)) or r["score_end"] - r["score_start"] != t["score_gain"]:
        fails.append(f"touching both coins changed score {r['score_start']} -> {r['score_end']} (expected +{t['score_gain']})")
if fails:
    print("FAIL:", "; ".join(fails))
    sys.exit(1)
print("PASS", r)
PY
