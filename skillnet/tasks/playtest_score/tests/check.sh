#!/bin/bash
# The answer must end with "Score: N" (or otherwise state the score last) and N must equal the true score.
set -uo pipefail
python3 - <<'PY'
import re, sys
truth = int(open("/task/truth/score.txt").read().strip())
try:
    ans = open("/task/answer.txt").read()
except FileNotFoundError:
    print("FAIL: no answer"); sys.exit(1)
m = re.findall(r"score\W{0,4}(?:is|of|=|:|will be|would be)?\W{0,4}(-?\d+)", ans, flags=re.I)
if not m:
    print("FAIL: no 'Score: N' in the answer"); sys.exit(1)
got = int(m[-1])
if got != truth:
    print(f"FAIL: answered {got}, true score {truth}"); sys.exit(1)
print("PASS", got)
PY
