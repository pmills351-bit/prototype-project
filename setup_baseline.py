# setup_baseline.py
from pathlib import Path

# --- settings ---
BASE = Path.cwd()  # or Path("path/to/your/project")
INPUT_DIR = BASE / "data" / "input"
MAP_DIR   = BASE / "data" / "mappings"
GOLD_DIR  = BASE / "data" / "golden"
OVERWRITE = False  # set to True if you want to overwrite files

# --- sample files ---
sample_csv = """MRN,RACE_DESC,ETHNICITY,SEX,BIRTH_DATE,MATCH_DATE,MATCH_FLAG,CONTACTED,IDENTIFIED,CONSENTED,ENROLLED,SCORE,CRITERIA_JSON,IDENTIFIED_AT,CONTACTED_AT
12345,Black,African American,F,1950-06-01,2025-08-01,1,1,1,0,0,0.82,"{\\"inc\\":[\\"EGFR+\\"],\\"exc\\":[\\"CrCl<60\\"]}",2025-08-01T10:00:00Z,2025-08-02T11:00:00Z
67890,White,Non-Hispanic,M,1975-02-20,2025-08-05,1,0,1,0,0,0.65,"{\\"inc\\":[\\"ALK+\\"],\\"exc\\":[]}",2025-08-05T09:30:00Z,
"""

mapping_yaml = """version: 1
schema_version: "1.0.0"
assign:
  site_id: "SITE_X"
  trial_id: "NCT01234567"
columns:
  patient_id: "hash(SALT, row.MRN)"
  race: "normalize_race(row.RACE_DESC)"
  ethnicity: "normalize_eth(row.ETHNICITY)"
  sex: "normalize_sex(row.SEX)"
  age: "years_between(row.BIRTH_DATE, row.MATCH_DATE)"
  eligible: "int(row.MATCH_FLAG)"
  selected: "int(row.CONTACTED)"
  identified: "int(row.IDENTIFIED)"
  contacted: "int(row.CONTACTED)"
  consented: "int(row.CONSENTED)"
  enrolled: "int(row.ENROLLED)"
  identified_at: "parse_dt(row.IDENTIFIED_AT)"
  contacted_at: "parse_dt(row.CONTACTED_AT)"
  match_score: "float(row.SCORE)"
  matched_criteria: "row.CRITERIA_JSON"
provenance:
  source_system: "demo_csv"
"""

def write_if_needed(path: Path, content: str, overwrite: bool = False):
    if path.exists() and not overwrite:
        print(f"SKIP (exists): {path}")
        return
    path.write_text(content, encoding="utf-8")
    print(f"WROTE: {path}")

def main():
    # 1) Make folders
    for p in [INPUT_DIR, MAP_DIR, GOLD_DIR]:
        p.mkdir(parents=True, exist_ok=True)
        print(f"DIR OK: {p}")

    # 2) Write sample input + mapping
    write_if_needed(INPUT_DIR / "sample_input.csv", sample_csv, OVERWRITE)
    write_if_needed(MAP_DIR / "mapping_demo.yaml", mapping_yaml, OVERWRITE)

    # 3) Leave golden/ empty — you’ll save your generated canonical output here
    print("\nNext steps:")
    print(" - Open Streamlit, run your mapping, then save the output CSV to data/golden/canonical_v1_golden.csv")
    print(" - Or script the mapping and write to that path programmatically.")

if __name__ == "__main__":
    main()
