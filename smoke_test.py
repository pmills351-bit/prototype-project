# smoke_test.py
import sys, subprocess, textwrap
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "out" / "smoke"
WORK.mkdir(parents=True, exist_ok=True)

SRC = WORK / "sample.csv"
MAP = WORK / "mapping.yaml"
CAN = WORK / "canonical.csv"
SEL = WORK / "selection_by_race.csv"
RR  = WORK / "rr_selection_by_race.csv"

def run_ok(args):
    cmd = [sys.executable, "-m", "trial_equity.cli"] + args
    r = subprocess.run(cmd, text=True, cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        print("STDOUT:\n", r.stdout)
        print("STDERR:\n", r.stderr)
        raise SystemExit(f"Command failed: {' '.join(cmd)}")
    return r

def write_sample_files():
    # NOTE: include the canonical-required fields as plain columns:
    # SITE_ID → site_id, TRIAL_ID → trial_id, AGE → age, SELECTED → selected
    rows = [
        # patient_id, RACE_DESC, ETHNICITY, SEX, BIRTH_DATE, MATCH_DATE,
        # MATCH_FLAG, CONTACTED, IDENTIFIED, CONSENTED, ENROLLED, SCORE,
        # CRITERIA_JSON, IDENTIFIED_AT, CONTACTED_AT,
        # SITE_ID, TRIAL_ID, AGE, SELECTED
        [11111,"Black","Not Hispanic","F","1960-01-15","2025-08-10",1,1,1,1,1,0.90,'{"inc":["EGFR+"],"exc":[]}',"2025-08-10T09:15:00Z","2025-08-10T10:00:00Z",
         "DEMO_SITE","TRIAL_X",65,1],
        [22222,"White","Not Hispanic","M","1970-03-02","2025-08-12",1,1,1,1,0,0.80,'{"inc":["ALK+"],"exc":[]}',"2025-08-12T08:40:00Z","2025-08-12T09:10:00Z",
         "DEMO_SITE","TRIAL_X",55,1],
        [33333,"White","Hispanic","F","1985-11-23","2025-08-05",1,0,1,0,0,0.70,'{"inc":["ROS1+"],"exc":[]}',"2025-08-05T13:20:00Z","",
         "DEMO_SITE","TRIAL_X",39,0],
        [55555,"Asian","Not Hispanic","F","1992-09-10","2025-08-04",1,1,1,0,0,0.60,'{"inc":["BRAF+"],"exc":[]}',"2025-08-04T11:05:00Z","2025-08-04T11:45:00Z",
         "DEMO_SITE","TRIAL_X",33,1],
    ]
    cols = [
        "patient_id","RACE_DESC","ETHNICITY","SEX","BIRTH_DATE","MATCH_DATE",
        "MATCH_FLAG","CONTACTED","IDENTIFIED","CONSENTED","ENROLLED","SCORE",
        "CRITERIA_JSON","IDENTIFIED_AT","CONTACTED_AT",
        "SITE_ID","TRIAL_ID","AGE","SELECTED"
    ]
    pd.DataFrame(rows, columns=cols).to_csv(SRC, index=False)

      # Minimal mapping: map required canonical columns 1:1 from the demo CSV
    MAP.write_text(textwrap.dedent("""\
        version: 1
        site_salt: TEST
        source:
          file: sample.csv
        columns:
          # canonical identity
          patient_id: patient_id
          site_id: SITE_ID
          trial_id: TRIAL_ID

          # demographics
          race: RACE_DESC
          ethnicity: ETHNICITY
          sex: SEX
          age: AGE

          # process flags
          eligible: MATCH_FLAG
          identified: IDENTIFIED
          contacted: CONTACTED
          consented: CONSENTED
          enrolled: ENROLLED
          selected: SELECTED

          # scoring + criteria + timestamps (optional but nice to have)
          score: SCORE
          matched_criteria: CRITERIA_JSON
          identified_at: IDENTIFIED_AT
          contacted_at: CONTACTED_AT

          # dates (not strictly required for the smoke path)
          match_date: MATCH_DATE
          birth_date: BIRTH_DATE
    """).strip(), encoding="utf-8")


def main():
    print(f"▶ Working dir: {WORK}")
    write_sample_files()

    print("▶ Map → canonical")
    run_ok(["map","--in",str(SRC),"--map",str(MAP),"--salt","TEST","--out",str(CAN)])
    assert CAN.exists() and CAN.stat().st_size > 0

    print("▶ Validate canonical")
    run_ok(["validate","--in",str(CAN)])

    print("▶ Audit selection by race")
    run_ok(["audit","--in",str(CAN),"--group","race","--metric","selection","--out",str(SEL)])
    assert SEL.exists() and SEL.stat().st_size > 0

    print("▶ Risk ratios (selection) vs White")
    run_ok(["rr","--in",str(CAN),"--group","race","--metric","selection","--ref","White","--out",str(RR)])
    assert RR.exists() and RR.stat().st_size > 0

    print("\n✅ Smoke test passed.")
    print(f"   Canonical: {CAN}")
    print(f"   Audit:     {SEL}")
    print(f"   RR:        {RR}")

if __name__ == "__main__":
    main()
