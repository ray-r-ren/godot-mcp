#!/bin/bash
# Pass when /task/outputs holds a zip with a complete Godot web export of Star Hop:
# an HTML page that loads the engine script, the engine .wasm, and a .pck whose header is GDPC.
set -uo pipefail
python3 - <<'PY'
import sys, zipfile, re
from pathlib import Path

outs = Path("/task/outputs")
zips = sorted(outs.rglob("*.zip")) if outs.exists() else []
if not zips:
    print("FAIL: no zip in outputs"); sys.exit(1)

def check(zp):
    try:
        zf = zipfile.ZipFile(zp)
    except zipfile.BadZipFile:
        return "not a zip"
    names = [n for n in zf.namelist() if not n.endswith("/")]
    html = [n for n in names if n.lower().endswith(".html")]
    wasm = [n for n in names if n.lower().endswith(".wasm")]
    pck = [n for n in names if n.lower().endswith(".pck")]
    js = [n for n in names if n.lower().endswith(".js")]
    if not (html and wasm and pck and js):
        return f"missing parts (html={len(html)}, wasm={len(wasm)}, pck={len(pck)}, js={len(js)})"
    w = zf.read(wasm[0])
    if w[:4] != b"\0asm" or len(w) < 1_000_000:
        return "the .wasm is not a WebAssembly engine binary"
    p = zf.read(pck[0])
    if p[:4] != b"GDPC":
        return "the .pck is not a Godot pack"
    page = zf.read(html[0]).decode("utf-8", "replace")
    js_base = [Path(j).name for j in js]
    if not any(b in page for b in js_base):
        return "the HTML page does not load the engine script"
    # The pack must hold this project's main scene (exported scenes are converted to .scn/.tscn.remap).
    if b"main" not in p or b"project.binary" not in p:
        return "the pack does not contain the Star Hop project"
    if "Star Hop" not in page and b"Star Hop" not in p:
        return "the build is not Star Hop"
    return None

errs = []
for z in zips:
    e = check(z)
    if e is None:
        print("PASS", z.name); sys.exit(0)
    errs.append(f"{z.name}: {e}")
print("FAIL:", "; ".join(errs)); sys.exit(1)
PY
