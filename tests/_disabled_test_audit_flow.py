import math
import pandas as pd

from trial_equity.mapping_runtime import apply_mapping
from trial_equity.normalize import normalize_race, normalize_eth, normalize_sex
from trial_equity.schema import validate_canonical_v1
from trial_equity.metrics import group_rate_ci

# --- Build a tiny rich dataset directly in memory (same as your rich CSV) ---
def _rich_df():
    rows = [
        # MRN, RACE_DESC, ETHNICITY, SEX, BIRTH_DATE, MATCH_DATE, MATCH_FLAG, CONTACTED, IDENTIFIED, CONSENTED, ENROLLED, SCORE, CRITERIA_JSON, IDENTIFIED_AT, CONTACTED_AT
        [11111, "Black", "Not Hispanic", "F", "1960-01-15", "2025-08-10", 1, 1, 1, 1, 1, 0.90, '{"inc":["EGFR+"],"exc":[]}', "2025-08-10T09:15:00Z", "2025-08-10T10:00:00Z"],
        [22222, "White", "Not Hispanic", "M", "1970-03-02", "2025-08-12", 1, 1, 1, 1, 0, 0.80, '{"inc":["ALK+"],"exc":[]}', "2025-08-12T08:40:00Z", "2025-08-12T09:10:00Z"],
        [33333, "White", "Hispanic", "F", "1985-11-23", "2025-08-05", 1, 0, 1, 0, 0, 0.70, '{"inc":["ROS1+"],"exc":[]}', "2025-08-05T13:20:00Z", ""],
        [44444, "Black", "Not Hispanic", "M", "1955-06-30", "2025-08-03", 0, 0, 1, 0, 0, 0.40, '{"inc":[],"exc":["GFR<60"]}', "2025-08-03T15:00:00Z", ""],
        [55555, "Asian", "Not Hispanic", "F", "1992-09-10", "2025-08-04", 1, 1, 1, 0, 0, 0.60, '{"inc":["BRAF+"],"exc":[]}', "2025-08-04T11:05:00Z", "2025-08-04T11:45:00Z"],
    ]
    return pd.DataFrame(rows, columns=[
        "MRN","RACE_DESC","ETHNICITY","SEX","BIRTH_DATE","MATCH_DATE",
        "MATCH_FLAG","CONTACTED","IDENTIFIED","CONSENTED","ENROLLED",
        "SCORE","CRITERIA_JSON","IDENTIFIED_AT","CONTACTED_AT"
    ])

# --- Minimal mapping (same expressions you use in the app) ---
_MAPPING = {
    "version": 1,
    "schema_version": "1.0.0",
    "assign": {"site_id": "SITE_X", "trial_id": "NCT01234567"},
    "columns": {
        "patient_id": "hash(SALT, row['MRN'])",
        "race": "normalize_race(row['RACE_DESC'])",
        "ethnicity": "normalize_eth(row['ETHNICITY'])",
        "sex": "normalize_sex(row['SEX'])",
        "age": "years_between(row['BIRTH_DATE'], row['MATCH_DATE'])",
        "eligible": "int(row['MATCH_FLAG'])",
        "selected": "int(row['CONTACTED'])",
        "identified": "int(row['IDENTIFIED'])",
        "contacted": "int(row['CONTACTED'])",
        "consented": "int(row['CONSENTED'])",
        "enrolled": "int(row['ENROLLED'])",
        "identified_at": "parse_dt(row['IDENTIFIED_AT'])",
        "contacted_at": "parse_dt(row['CONTACTED_AT'])",
        "match_score": "float(row['SCORE'])",
        "matched_criteria": "str(row['CRITERIA_JSON'])",
    },
    "provenance": {"source_system": "test_df"},
}

def _coerce_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["eligible","selected","identified","contacted","consented","enrolled"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    return out

def test_end_to_end_fairness_by_race():
    # 1) Source → Canonical
    df_in = _rich_df()
    df_out = apply_mapping(df_in, _MAPPING, default_site_salt="TEST_SALT")

    # 2) Normalize enums (belt & suspenders)
    df_out["race"] = df_out["race"].apply(normalize_race)
    df_out["ethnicity"] = df_out["ethnicity"].apply(normalize_eth)
    df_out["sex"] = df_out["sex"].apply(normalize_sex)
    df_out = _coerce_flags(df_out)

    # 3) Validate schema
    validate_canonical_v1(df_out)

    # 4) Selection Parity: Contacted | Eligible
    sel = group_rate_ci(df_out, group_col="race", num_col="contacted", den_cond_col="eligible")
    sel_rates = {r["race"]: r["rate"] for _, r in sel.iterrows()}
    assert round(sel_rates["Black or African American"], 3) == 1.000
    assert round(sel_rates["White"], 3) == 0.500
    assert round(sel_rates["Asian"], 3) == 1.000

    # 5) Opportunity Parity: Consented | Contacted
    opp = group_rate_ci(df_out, group_col="race", num_col="consented", den_cond_col="contacted")
    opp_rates = {r["race"]: r["rate"] for _, r in opp.iterrows()}
    assert round(opp_rates["Black or African American"], 3) == 1.000
    assert round(opp_rates["White"], 3) == 1.000
    assert round(opp_rates["Asian"], 3) == 0.000

    # 6) Enrollment: Enrolled | Consented
    enr = group_rate_ci(df_out, group_col="race", num_col="enrolled", den_cond_col="consented")
    enr_rates = {r["race"]: r["rate"] for _, r in enr.iterrows()}
    # Black: 1/1; White: 0/1; Asian: denominator 0 -> NaN
    assert round(enr_rates["Black or African American"], 3) == 1.000
    assert round(enr_rates["White"], 3) == 0.000
    assert math.isnan(enr_rates["Asian"])
