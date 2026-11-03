#!/bin/bash
# The answer must name the parse error (player.gd, line 9) and the missing script (frog_ai.gd) on ERROR lines.
set -uo pipefail
python3 - <<'PY'
import json, re, sys
t = json.load(open("/task/truth/expected.json"))
try:
    ans = open("/task/answer.txt", encoding="utf-8", errors="replace").read()
except FileNotFoundError:
    print("FAIL: no answer"); sys.exit(1)
lines = [l for l in ans.splitlines() if "ERROR" in l.upper()]
fails = []
parse_ok = any(t["parse_file"] in l and re.search(r"(?<!\d)%d(?!\d)" % t["parse_line"], l) for l in lines)
if not parse_ok:
    fails.append(f"no ERROR line naming {t['parse_file']} with line {t['parse_line']}")
if not any(t["missing_file"] in l for l in lines):
    fails.append(f"no ERROR line naming the missing {t['missing_file']}")
if fails:
    print("FAIL:", "; ".join(fails)); print(ans[-1500:]); sys.exit(1)
print("PASS")
PY
