#!/usr/bin/env python
"""
Minimal, CI-friendly smoke test for the Trial Equity CLI.

- Generates a small "rich" input CSV.
- Uses repo mapping at data/mappings/mapping_demo.yaml if available
  (falls back to a minimal inline mapping if not).
- Runs: map → validate → audit(selection by race) → rr(selection vs ref).
- Always calls the CLI via:  python -m trial_equity.cli
"""

from __future__ import annotations
import sys
import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "out" / "smoke"
WORK.mkdir(parents=True, exist_ok=True)

SRC = WORK / "sample.csv"
MAP = ROOT / "data" / "mappings" / "mapping_demo.yaml"
MAP_FALLBACK = WORK / "mapping_fallback.yaml"
CANON = WORK / "canonical.csv"
AUDIT = WORK / "selection_by_race.csv"
RR = WORK / "rr_selection_by_race.csv"


def _print(step: str) -> None:
    print(step, flush=True)


def run_ok(args: list[str], cwd: Path | None = None) -> None:
    """
    Run the Trial Equity CLI reliably in any environment by invoking:
    python -m trial_equity.cli <args>
    """
    cmd = [sys.executable, "-m", "trial_equity.cli"] + args
    r = subprocess.run(cmd, text=True, cwd=cwd, capture_output=True)
    if r.returncode != 0:
        msg = (
            f"FAILED: {' '.join(cmd)}\n"
            f"STDOUT:\n{r.stdout}\n"
            f"STDERR:\n{r.stderr}"
        )
        raise SystemExit(msg)


def write_sample_csv(path: Path) -> None:
    """
    Write a tiny 'rich' source CSV compatible with mapping_demo.yaml.
    Columns mirror the sample you’ve been using in local runs/CI.
    """
    rows = [
        [11111, "Black", "Not Hispanic", "F", "1960-01-15", "2025-08-10", 1, 1, 1, 1, 1, 0.90, {"inc": ["EGFR+"], "exc": []}, "2025-08-10T09:15:00Z", "2025-08-10T10:00:00Z"],
        [22222, "White", "Not Hispanic", "M", "1970-03-02", "2025-08-12", 1, 1, 1, 1, 0, 0.80, {"inc": ["ALK+"], "exc": []}, "2025-08-12T08:40:00Z", "2025-08-12T09:10:00Z"],
        [33333, "White", "Hispanic", "F", "1985-11-23", "2025-08-05", 1, 0, 1, 0, 0, 0.70, {"inc": ["ROS1+"], "exc": []}, "2025-08-05T13:20:00Z", ""],
        [44444, "Black", "Not Hispanic", "M", "1955-06-30", "2025-08-03", 0, 0, 1, 0, 0, 0.40, {"inc": [], "exc": ["GFR<60"]}, "2025-08-03T15:00:00Z", ""],
        [55555, "Asian", "Not Hispanic", "F", "1992-09-10", "2025-08-04", 1, 1, 1, 0, 0, 0.60, {"inc": ["BRAF+"], "exc": []}, "2025-08-04T11:05:00Z", "2025-08-04T11:45:00Z"],
    ]
    cols = [
        "MRN", "RACE_DESC", "ETHNICITY", "SEX", "BIRTH_DATE", "MATCH_DATE",
        "MATCH_FLAG", "CONTACTED", "IDENTIFIED", "CONSENTED", "ENROLLED",
        "SCORE", "CRITERIA_JSON", "IDENTIFIED_AT", "CONTACTED_AT"
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            r2 = r.copy()
            # ensure CRITERIA_JSON is a JSON string
            r2[12] = json.dumps(r2[12])
            w.writerow(r2)


def ensure_mapping() -> Path:
    """
    Prefer repo mapping (data/mappings/mapping_demo.yaml). If not found,
    write a minimal fallback mapping that covers the required schema.
    """
    if MAP.exists():
        return MAP

    # Minimal fallback: map source → canonical v1 columns your validator expects.
    MAP_FALLBACK.write_text(
        """
version: 1
source:
  format: csv
  path: sample.csv

columns:
  patient_id: MRN
  race: RACE_DESC
  ethnicity: ETHNICITY
  sex: SEX
  selected: MATCH_FLAG
  eligible: MATCH_FLAG
  contacted: CONTACTED
  consented: CONSENTED
  enrolled: ENROLLED
  matched_criteria: CRITERIA_JSON
  identified_at: IDENTIFIED_AT
  contacted_at: CONTACTED_AT

literals:
  site_id: "SITE_A"
  trial_id: "TRIAL_X"
  schema_version: "v1"
  source_system: "smoke_test"
        """.strip(),
        encoding="utf-8",
    )
    return MAP_FALLBACK


def main() -> None:
    print(f"▶ Working dir: {WORK}")
    write_sample_csv(SRC)
    map_path = ensure_mapping()

    _print("▶ Map → canonical")
    run_ok(["map", "--in", str(SRC), "--map", str(map_path), "--salt", "TEST", "--out", str(CANON)])

    _print("▶ Validate canonical")
    run_ok(["validate", "--in", str(CANON)])

    _print("▶ Audit selection by race")
    run_ok(["audit", "--in", str(CANON), "--group", "race", "--metric", "selection", "--out", str(AUDIT)])

    # Use "White" as the default reference; your sample ensures denom > 0 for White.
    _print("▶ Risk ratios (selection) vs White")
    run_ok(["rr", "--in", str(CANON), "--group", "race", "--metric", "selection", "--ref", "White", "--out", str(RR)])

    print(
        "\n✅ Smoke test passed.\n"
        f"   Canonical: {CANON}\n"
        f"   Audit:     {AUDIT}\n"
        f"   RR:        {RR}"
    )


if __name__ == "__main__":
    main()
