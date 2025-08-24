# fix_sample.py
import pandas as pd
from pathlib import Path

rows = [
    {
        "MRN": 12345,
        "RACE_DESC": "Black",
        "ETHNICITY": "Not Hispanic",
        "SEX": "F",
        "BIRTH_DATE": "1950-06-01",
        "MATCH_DATE": "2025-08-01",
        "MATCH_FLAG": 1,
        "CONTACTED": 1,
        "IDENTIFIED": 1,
        "CONSENTED": 0,
        "ENROLLED": 0,
        "SCORE": 0.82,
        "CRITERIA_JSON": '{"inc":["EGFR+"],"exc":["CrCl<60"]}',
        "IDENTIFIED_AT": "2025-08-01T10:00:00Z",
        "CONTACTED_AT": "2025-08-02T11:00:00Z",
    },
    {
        "MRN": 67890,
        "RACE_DESC": "White",
        "ETHNICITY": "Not Hispanic",
        "SEX": "M",
        "BIRTH_DATE": "1975-02-20",
        "MATCH_DATE": "2025-08-05",
        "MATCH_FLAG": 1,
        "CONTACTED": 0,
        "IDENTIFIED": 1,
        "CONSENTED": 0,
        "ENROLLED": 0,
        "SCORE": 0.65,
        "CRITERIA_JSON": '{"inc":["ALK+"],"exc":[]}',
        "IDENTIFIED_AT": "2025-08-05T09:30:00Z",
        "CONTACTED_AT": "",
    },
]

df = pd.DataFrame(rows, columns=[
    "MRN","RACE_DESC","ETHNICITY","SEX","BIRTH_DATE","MATCH_DATE",
    "MATCH_FLAG","CONTACTED","IDENTIFIED","CONSENTED","ENROLLED",
    "SCORE","CRITERIA_JSON","IDENTIFIED_AT","CONTACTED_AT"
])

out = Path("data/input/sample_input.csv")
out.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out, index=False)
print(f"Wrote clean sample to {out.resolve()}")
