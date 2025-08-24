import pandas as pd

# Canonical enums
RACE = [
    "White",
    "Black or African American",
    "Asian",
    "American Indian or Alaska Native",
    "Native Hawaiian or Other Pacific Islander",
    "Multiple",
    "Unknown",
    "Declined",
]
ETHN = ["Hispanic or Latino", "Not Hispanic or Latino", "Unknown", "Declined"]
SEX  = ["Female", "Male", "Intersex", "Unknown", "Declined"]

# Required columns for Canonical v1
REQUIRED = [
    "patient_id", "site_id", "trial_id",
    "race", "ethnicity", "sex",
    "age", "eligible", "selected",
]

def validate_canonical_v1(df: pd.DataFrame) -> None:
    """
    Lightweight validator for Canonical v1.
    Raises ValueError with a helpful message if invalid; otherwise returns None.
    """
    # 1) Required columns present?
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # 2) Categories within enums
    if not set(df["race"].dropna()).issubset(RACE):
        bad = sorted(set(df["race"].dropna()) - set(RACE))
        raise ValueError(f"Non-canonical race values: {bad}")
    if not set(df["ethnicity"].dropna()).issubset(ETHN):
        bad = sorted(set(df["ethnicity"].dropna()) - set(ETHN))
        raise ValueError(f"Non-canonical ethnicity values: {bad}")
    if not set(df["sex"].dropna()).issubset(SEX):
        bad = sorted(set(df["sex"].dropna()) - set(SEX))
        raise ValueError(f"Non-canonical sex values: {bad}")

    # 3) Eligible/selected must be 0/1
    for col in ["eligible", "selected"]:
        vals = pd.to_numeric(df[col], errors="coerce").dropna().unique()
        if not set(vals).issubset({0, 1}):
            raise ValueError(f"{col} must be 0/1. Got {sorted(vals.tolist())}")

    # 4) Age must be >= 0 when present
    if "age" in df.columns:
        ages = pd.to_numeric(df["age"], errors="coerce")
        if (ages < 0).any():
            raise ValueError("Age must be >= 0.")

    # If we got here, it's valid.
    return None
