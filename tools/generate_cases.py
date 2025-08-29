# tools/generate_cases.py
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def _write(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)

def make_rich_source() -> pd.DataFrame:
    rows = [
        [11111, "Black", "Not Hispanic", "F", "1960-01-15", "2025-08-10", 1, 1, 1, 1, 1, 0.90, '{"inc":["EGFR+"],"exc":[]}', "2025-08-10T09:15:00Z", "2025-08-10T10:00:00Z"],
        [22222, "White", "Not Hispanic", "M", "1970-03-02", "2025-08-12", 1, 1, 1, 1, 0, 0.80, '{"inc":["ALK+"],"exc":[]}',  "2025-08-12T08:40:00Z", "2025-08-12T09:10:00Z"],
        [33333, "White", "Hispanic",     "F", "1985-11-23", "2025-08-05", 1, 0, 1, 0, 0, 0.70, '{"inc":["ROS1+"],"exc":[]}', "2025-08-05T13:20:00Z", ""],
        [44444, "Black", "Not Hispanic", "M", "1955-06-30", "2025-08-03", 0, 0, 1, 0, 0, 0.40, '{"inc":[],"exc":["GFR<60"]}',"2025-08-03T15:00:00Z", ""],
        [55555, "Asian", "Not Hispanic", "F", "1992-09-10", "2025-08-04", 1, 1, 1, 0, 0, 0.60, '{"inc":["BRAF+"],"exc":[]}', "2025-08-04T11:05:00Z", "2025-08-04T11:45:00Z"],
    ]
    cols = [
        "MRN","RACE_DESC","ETHNICITY","SEX","BIRTH_DATE","MATCH_DATE",
        "MATCH_FLAG","CONTACTED","IDENTIFIED","CONSENTED","ENROLLED",
        "SCORE","CRITERIA_JSON","IDENTIFIED_AT","CONTACTED_AT"
    ]
    return pd.DataFrame(rows, columns=cols)

def main() -> None:
    demo_dir = ROOT / "data" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)

    # 1) source CSV
    src = make_rich_source()
    _write(demo_dir / "sample_input_rich.csv", src)

    # 2) mapping YAML (kept simple on purpose)
    mapping_yaml = """
columns:
  patient_id: MRN
  race: RACE_DESC
  ethnicity: ETHNICITY
  sex: SEX
  birth_date: BIRTH_DATE
  match_date: MATCH_DATE
  eligible: MATCH_FLAG
  identified: IDENTIFIED
  contacted: CONTACTED
  consented: CONSENTED
  enrolled: ENROLLED
  match_score: SCORE
  matched_criteria: CRITERIA_JSON

literals:
  site_id: "SITE_DEMO"
  trial_id: "NCT01234567"
  source_system: "demo_csv"
  schema_version: "1.0.0"
"""
    (demo_dir / "mapping_demo.yaml").write_text(mapping_yaml.strip(), encoding="utf-8")

    print("OK: wrote demo data to", demo_dir)

if __name__ == "__main__":
    main()
