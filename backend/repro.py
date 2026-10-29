"""Regenerate twice with the same seed and compare checksums (Windows-friendly replacement for repro.sh). Run from backend/."""
import hashlib, pathlib, subprocess, sys
for d in ("data_a", "data_b"):
    subprocess.run([sys.executable, "generate.py", "--out", d], check=True, stdout=subprocess.DEVNULL)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
bad = 0
for f in sorted(list(pathlib.Path("data_a").glob("*.csv")) + [pathlib.Path("data_a/seed.sql"), pathlib.Path("data_a/validation_summary.json")]):
    g = pathlib.Path("data_b") / f.name
    same = sha(f) == sha(g); bad += not same
    print(("OK       " if same else "MISMATCH ") + f.name, sha(f)[:12])
sys.exit(1 if bad else 0)