#!/bin/bash
# Independent check: run the delivered project headlessly at 60 fps with a probe autoload; the Countdown Timer must
# exist, have its timeout connected to the main scene, and lower time_left from 60 by 2-3 after 2.5 s of game time.
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
    fails.append("the probe did not finish (game did not start)")
else:
    if not r["timer"]:
        fails.append("no Timer named Countdown in the main scene")
    elif abs((r["wait_time"] or 0) - 1.0) > 0.01:
        fails.append(f"Countdown wait_time is {r['wait_time']}, not 1 s")
    if not r["connected_to_main"]:
        fails.append(f"Countdown.timeout is not connected to the main scene ({r['connections']} connection(s))")
    if r["time_left_start"] != t["start"]:
        fails.append(f"time_left starts at {r['time_left_start']}, not {t['start']}")
    elif not isinstance(r["time_left_end"], (int, float)) or not (t["ticks_after_2_5s"][0] <= t["start"] - r["time_left_end"] <= t["ticks_after_2_5s"][1]):
        fails.append(f"after 2.5 s time_left is {r['time_left_end']} (expected 57 or 58)")
    if not r["label_shows_time"]:
        fails.append("no visible label shows the time left")
    if not r["player_body"]:
        fails.append("no CharacterBody player in the main scene")
    if not r["jump_action"]:
        fails.append("no jump input action")
if o["errors"]:
    fails.append("engine errors: " + " | ".join(o["errors"][:3]))
if fails:
    print("FAIL:", "; ".join(fails)); sys.exit(1)
print("PASS", r)
PY
