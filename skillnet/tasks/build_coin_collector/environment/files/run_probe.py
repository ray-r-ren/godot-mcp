"""Find the delivered Godot project zip, run it headlessly with an independent probe, print the measurements."""
import json, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOISE = ("V-Sync", "XOpenIM", "audio", "Audio", "ALSA", "PulseAudio", "pulse")


def find_project_zip(root: Path):
    cands = []
    for z in root.rglob("*.zip"):
        try:
            with zipfile.ZipFile(z) as zf:
                names = zf.namelist()
        except zipfile.BadZipFile:
            continue
        pg = [n for n in names if n.endswith("project.godot") and n.count("/") <= 1]
        if pg:
            cands.append((z.stat().st_mtime, z, pg[0]))
    cands.sort()
    return cands[-1] if cands else None


def extract(z: Path, inner: str) -> Path:
    dest = Path(tempfile.mkdtemp(prefix="probe-"))
    with zipfile.ZipFile(z) as zf:
        for m in zf.infolist():
            p = (dest / m.filename).resolve()
            if not str(p).startswith(str(dest)):
                continue
            if m.is_dir():
                p.mkdir(parents=True, exist_ok=True)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(zf.read(m))
    return (dest / inner).parent


def errors_in(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        if ln.startswith(("SCRIPT ERROR:", "ERROR:", "USER SCRIPT ERROR:")) and not any(n in ln for n in NOISE):
            out.append(ln.strip())
    return out


def main() -> int:
    found = find_project_zip(Path(sys.argv[1]))
    if not found:
        print("FAIL: no zip with a Godot project.godot in the outputs")
        return 2
    _, z, inner = found
    proj = extract(z, inner)
    print("project:", z.name)
    shutil.copy(HERE / "probe.gd", proj / "zz_probe.gd")
    pg = (proj / "project.godot").read_text()
    if "[autoload]" in pg:
        pg = pg.replace("[autoload]", '[autoload]\n\nZZProbe="*res://zz_probe.gd"', 1)
    else:
        pg += '\n[autoload]\n\nZZProbe="*res://zz_probe.gd"\n'
    (proj / "project.godot").write_text(pg)
    env = dict(os.environ, HOME=tempfile.mkdtemp(prefix="probe-home-"))
    subprocess.run(["godot", "--headless", "--path", str(proj), "--import"], capture_output=True, text=True, timeout=180, env=env)
    r = subprocess.run(["godot", "--headless", "--path", str(proj), "--fixed-fps", "60", "--audio-driver", "Dummy",
                        "--quit-after", "3000"], capture_output=True, text=True, timeout=240, env=env)
    m = re.search(r"PROBE_RESULT (\{.*\})", r.stdout)
    result = json.loads(m.group(1)) if m else None
    errs = errors_in(r.stderr + "\n" + r.stdout)
    out = {"result": result, "errors": errs[:20], "exit": r.returncode}
    print(json.dumps(out, indent=1))
    Path(os.environ.get("PROBE_OUT", "/tmp/probe_out.json")).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
