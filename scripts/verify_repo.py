#!/usr/bin/env python3
"""Repository integrity / syntax check that does not transmit network traffic."""
from __future__ import annotations

import argparse
import hashlib
import py_compile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    ROOT / "src/phase1/sender.py",
    ROOT / "src/phase1/receiver.py",
    ROOT / "src/phase2/mcast_canvas.py",
    ROOT / "original_submission/NE_Phase_001_Sepehr_Rajabi/Phase_001_Report.pdf",
    ROOT / "original_submission/NE_Phase_002_Sepehr_Rajabi/Phase_002_Report.pdf",
    ROOT / "original_submission/NE_Phase_002_Sepehr_Rajabi/NE_Video.mp4",
    ROOT / "original_submission/NE_Phase_002_Sepehr_Rajabi/Wireshark.pcapng",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Check required project files and Python syntax.")
    ap.add_argument("--verify-originals", action="store_true", help="Also verify SHA-256 values in MANIFEST.sha256.")
    args = ap.parse_args()

    missing = [p for p in EXPECTED if not p.exists()]
    if missing:
        print("Missing required files:")
        for p in missing:
            print(" -", p.relative_to(ROOT))
        return 1

    for p in [ROOT / "src/phase1/sender.py", ROOT / "src/phase1/receiver.py", ROOT / "src/phase2/mcast_canvas.py"]:
        with tempfile.NamedTemporaryFile(suffix=".pyc") as tmp:
            py_compile.compile(str(p), cfile=tmp.name, doraise=True)
        print("syntax OK:", p.relative_to(ROOT))

    if args.verify_originals:
        manifest = ROOT / "MANIFEST.sha256"
        failures = []
        for raw in manifest.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            expected, rel = raw.split("  ", 1)
            p = ROOT / rel
            if not p.exists() or sha256(p) != expected:
                failures.append(rel)
        if failures:
            print("SHA-256 verification failed:")
            for rel in failures:
                print(" -", rel)
            return 2
        print("original-file SHA-256 verification: OK")

    print("repository verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
