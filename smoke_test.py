# smoke_test.py
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "smoke"
OUT.mkdir(parents=True, exist_ok=True)

def run(cmd: list[str]) -> None:
    print("▶", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip())
    proc.check_returncode()

def main():
    print(f"▶ Working dir: {OUT}")
    # Map -> canonical (NO --salt)
    print("▶ Map → canonical")
    run([
        "python", "-m", "trial_equity.cli", "map",
        "--in", "data/cases/case-basic/sample.csv",
        "--map", "data/cases/case-basic/mapping.yaml",
        "--out", str(OUT / "canonical.csv"),
    ])

    # Validate
    print("▶ Validate canonical")
    run([
        "python", "-m", "trial_equity.cli", "validate",
        "--in", str(OUT / "canonical.csv"),
    ])

    # Audit
    print("▶ Audit selection by race")
    run([
        "python", "-m", "trial_equity.cli", "audit",
        "--in", str(OUT / "canonical.csv"),
        "--group", "race",
        "--metric", "selection",
        "--out", str(OUT / "selection_by_race.csv"),
    ])

    # Risk ratios
    print("▶ Risk ratios (selection) vs White")
    run([
        "python", "-m", "trial_equity.cli", "rr",
        "--in", str(OUT / "canonical.csv"),
        "--group", "race",
        "--metric", "selection",
        "--ref", "White",
        "--out", str(OUT / "rr_selection_by_race.csv"),
    ])

    print("\n✅ Smoke test passed.")
    print(f"   Canonical: {OUT / 'canonical.csv'}")
    print(f"   Audit:     {OUT / 'selection_by_race.csv'}")
    print(f"   RR:        {OUT / 'rr_selection_by_race.csv'}")

if __name__ == "__main__":
    main()
