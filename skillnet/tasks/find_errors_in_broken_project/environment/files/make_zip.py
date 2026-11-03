"""Zip a folder byte-for-byte deterministically (sorted names, fixed timestamps)."""
import sys, zipfile
from pathlib import Path

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
top = sys.argv[3] if len(sys.argv) > 3 else ""
with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
    for p in sorted(src.rglob("*")):
        if p.is_file():
            arc = p.relative_to(src).as_posix()
            info = zipfile.ZipInfo((top + "/" if top else "") + arc, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())
