#!/bin/bash
# Independent check: run the delivered project headlessly with a probe that holds move_right, then touches every coin.
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
if r is None:
    fails.append("the probe did not finish (game did not start or hung)")
else:
    if not r["player"]:
        fails.append("no node in group 'player' (or named Player)")
    if r["moved"] < t["min_move_px"]:
        fails.append(f"holding move_right moved the player only {r['moved']} px")
    if r["coins_initial"] < t["min_coins"]:
        fails.append(f"only {r['coins_initial']} coins in group 'coins'")
    if not isinstance(r["score_start"], (int, float)):
        fails.append("no numeric `score` on the main scene root")
    else:
        if r["score_after_one"] != r["score_before_pickups"] + t["score_per_coin"]:
            fails.append(f"one coin changed score {r['score_before_pickups']} -> {r['score_after_one']}")
        if r["score_end"] - r["score_start"] != r["coins_initial"] * t["score_per_coin"]:
            fails.append(f"collecting all {r['coins_initial']} coins gave score {r['score_start']} -> {r['score_end']}")
    if not r["win_text"]:
        fails.append("no visible 'You win' text after all coins were collected")
if o["errors"]:
    fails.append("engine errors: " + " | ".join(o["errors"][:3]))
if fails:
    print("FAIL:", "; ".join(fails))
    sys.exit(1)
print("PASS", r)
PY
