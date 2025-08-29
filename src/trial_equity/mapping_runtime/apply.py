# src/trial_equity/mapping_runtime/apply.py
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
import hashlib
import inspect
from datetime import datetime, timezone
import pandas as pd

from .envy import _build_eval_env
from ..normalize import normalize_race, normalize_eth, normalize_sex

# Canonical surface columns expected by tests
CanonicalCols = ("race", "ethnicity", "sex", "eligible", "selected")

# ---------------------------- helpers --------------------------------------------

def _stable_hash(val: Any, salt: str) -> str:
    return hashlib.sha256(f"{val}|{salt}".encode("utf-8")).hexdigest()[:16]

def _find_ci(df: pd.DataFrame, name: str) -> Optional[str]:
    """Find a column by name, case-insensitively, returning the actual column name."""
    t = str(name).lower()
    for c in df.columns:
        if str(c).lower() == t:
            return c
    return None

def _all_na(series: pd.Series) -> bool:
    try:
        return series.isna().all()
    except Exception:
        return False

def _as_int_flag(x: Any) -> int:
    if x is None:
        return 0
    try:
        import pandas as _pd
        if _pd.isna(x):
            return 0
    except Exception:
        pass
    if isinstance(x, (int, float)):
        return 1 if float(x) != 0.0 else 0
    s = str(x).strip().lower()
    if s in {"1", "true", "t", "y", "yes"}:
        return 1
    if s in {"0", "false", "f", "n", "no"}:
        return 0
    return 1 if s else 0

def _looks_like_timestamp_string(series: pd.Series) -> bool:
    if series.dtype != object:
        return False
    sample = series.dropna().astype(str).head(5)
    return any(("t" in v.lower() or "-" in v or ":" in v) for v in sample)

def _flag_from_column(df: pd.DataFrame, name: str) -> Optional[pd.Series]:
    """Return a 0/1 Series from a single named column (CI match) if present."""
    col = _find_ci(df, name)
    if col is None:
        return None
    s = df[col]
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.notna().astype(int)
    if _looks_like_timestamp_string(s):
        return s.astype(str).str.strip().ne("").astype(int)
    return s.map(_as_int_flag)

def _eval_rowwise(df: pd.DataFrame, expr: str) -> pd.Series:
    """
    Evaluate a Python expression per row with a safe helper env.
    Example expr: "normalize_eth(row['ETHNICITY'])", "int(row['CONTACTED'])"
    """
    env = _build_eval_env(
        normalize_race=normalize_race,
        normalize_eth=normalize_eth,
        normalize_sex=normalize_sex,
        int=int, float=float, str=str, bool=bool, len=len,
    )
    def _do(r):
        return eval(expr, {"__builtins__": {}}, {**env, "row": r})
    return df.apply(_do, axis=1)

# ---------------------------- main -----------------------------------------------

def apply_mapping(
    df_in: pd.DataFrame,
    mapping: Mapping[str, Any],
    *,
    default_site_salt: str = "",
) -> pd.DataFrame:
    """
    Apply a flexible mapping to produce canonical columns for auditing.

    Returns a DataFrame with (at least):
      race, ethnicity, sex, eligible, selected,
      patient_id_raw, patient_id, patient_id_hash,
      contacted, consented, enrolled, site_id, trial_id, age
    """
    if not isinstance(df_in, pd.DataFrame):
        raise TypeError("apply_mapping: df_in must be a pandas DataFrame")

    df = df_in.copy()
    lower_to_actual = {str(c).lower(): c for c in df.columns}

    # 1) Apply mapping["columns"] conservatively (avoid renaming to expressions)
    colmap: Dict[str, str] = dict(mapping.get("columns", {})) or {}
    for k, v in list(colmap.items()):
        k_l, v_s = str(k).lower(), str(v)
        src_actual = lower_to_actual.get(k_l)

        # Case A: src -> canonical rename (only if dest is a simple column name)
        if src_actual is not None and "[" not in v_s and "(" not in v_s and " " not in v_s:
            df = df.rename(columns={src_actual: v_s})
            continue

        # Case B: canonical -> src copy
        src_actual = lower_to_actual.get(str(v).lower())
        if src_actual is not None and "[" not in str(k) and "(" not in str(k) and " " not in str(k):
            df[str(k)] = df[src_actual]

    # 2) Apply mapping["assign"] (constants / callables / row-wise expressions)
    assigns: Mapping[str, Any] = mapping.get("assign", {}) or {}
    for col, val in assigns.items():
        if callable(val):
            df[col] = val(df)
        elif isinstance(val, str):
            # Treat as expression if it references row or looks like a call
            if "row[" in val or (("(" in val) and (")" in val)):
                try:
                    df[col] = _eval_rowwise(df, val)
                except Exception:
                    df[col] = val  # degrade gracefully
            else:
                df[col] = val
        else:
            df[col] = val

    # 3) Ensure canonical columns exist
    for c in CanonicalCols:
        if c not in df.columns:
            df[c] = 0 if c in ("eligible", "selected") else None

    # 4) Backfill enums from obvious source fields if missing/all-null
    if "race" not in df.columns or _all_na(df["race"]):
        for nm in ["RACE_DESC", "RACE", "Race", "race", "PAT_RACE", "PATIENT_RACE"]:
            col = _find_ci(df, nm)
            if col:
                df["race"] = df[col]
                break
    if "ethnicity" not in df.columns or _all_na(df["ethnicity"]):
        for nm in ["ETHNICITY", "ETH", "ethnicity", "PAT_ETHNICITY"]:
            col = _find_ci(df, nm)
            if col:
                df["ethnicity"] = df[col]
                break
    if "sex" not in df.columns or _all_na(df["sex"]):
        for nm in ["SEX", "sex", "Gender", "gender", "GENDER", "biological_sex"]:
            col = _find_ci(df, nm)
            if col:
                df["sex"] = df[col]
                break

    # Keep eth <-> ethnicity alias
    eth_col = _find_ci(df, "eth")
    if "ethnicity" not in df.columns and eth_col:
        df["ethnicity"] = df[eth_col]
    elif eth_col is None and "ethnicity" in df.columns:
        df["eth"] = df["ethnicity"]

    # 5) Eligible (drive by MATCH_* first; then ELIGIBLE*; then IDENTIFIED; then IDENTIFIED_AT)
    derived = None
    # a) strongest: explicit match flags
    for nm in ["MATCH_FLAG", "MATCHED", "MATCH"]:
        s = _flag_from_column(df, nm)
        if s is not None:
            derived = s.astype(int)
            break
    # b) explicit eligible flags
    if derived is None:
        for nm in ["ELIGIBLE", "ELIG", "IS_ELIGIBLE"]:
            s = _flag_from_column(df, nm)
            if s is not None:
                derived = s.astype(int)
                break
    # c) identified flag
    if derived is None:
        s = _flag_from_column(df, "IDENTIFIED")
        if s is not None:
            derived = s.astype(int)
    # d) identified timestamp presence
    if derived is None:
        s = _flag_from_column(df, "IDENTIFIED_AT")
        if s is not None:
            derived = s.astype(int)

    # If an existing 'eligible' exists and sums to zero, replace with derived if available
    if "eligible" in df.columns:
        cur = df["eligible"].map(_as_int_flag).astype(int)
        if cur.sum() == 0 and derived is not None:
            df["eligible"] = derived
        else:
            df["eligible"] = cur if derived is None else derived
    else:
        df["eligible"] = 0 if derived is None else derived

    # 6) Selected (respect existing, else derive from obvious flags)
    sel = None
    for nm in ["SELECTED", "IS_SELECTED", "SELECTED_FLAG", "ENROLLED"]:
        s = _flag_from_column(df, nm)
        if s is not None:
            sel = s.astype(int)
            break
    if "selected" in df.columns:
        cur = df["selected"].map(_as_int_flag).astype(int)
        df["selected"] = cur if sel is None else sel
    else:
        df["selected"] = 0 if sel is None else sel

    # 7) Patient ID & salted hash
    #    - patient_id_raw: source identifier (MRN/subject_id/etc.)
    #    - patient_id_hash: salted deterministic hash
    #    - patient_id: the salted hash (so it changes with site salt, as tests expect)
    pid_col = None
    for nm in ["patient_id", "PATIENT_ID", "MRN", "mrn", "subject_id", "SUBJECT_ID", "id", "ID"]:
        col = _find_ci(df, nm)
        if col:
            pid_col = col
            break

    # Create a Series regardless of source
    if pid_col is not None:
        patient_id_raw = df[pid_col].astype(str)
    else:
        # fallback: use the row index, but ensure it's a Series aligned to df
        patient_id_raw = pd.Series(df.index.astype(str), index=df.index)

    salt = str(mapping.get("site_salt", "")) or str(default_site_salt or "")

    # Ensure Series, then hash
    if not isinstance(patient_id_raw, pd.Series):
        patient_id_raw = pd.Series(patient_id_raw, index=df.index).astype(str)
    else:
        patient_id_raw = patient_id_raw.astype(str)

    patient_id_hash = patient_id_raw.apply(lambda x: _stable_hash(x, salt))

    df["patient_id_raw"] = patient_id_raw
    df["patient_id_hash"] = patient_id_hash
    # IMPORTANT: for tests, the public patient_id must change with salt
    df["patient_id"] = patient_id_hash

    # 7.5) site_id / trial_id backfill (case-insensitive; accept common aliases)
    if "site_id" not in df.columns or _all_na(df.get("site_id", pd.Series(dtype=object))):
        site_src = None
        for nm in ["site_id", "SITE_ID", "source_site_id", "site", "SITE"]:
            site_src = _find_ci(df, nm)
            if site_src:
                df["site_id"] = df[site_src]
                break
        if site_src is None:
            df["site_id"] = "SITE_UNKNOWN"

    if "trial_id" not in df.columns or _all_na(df.get("trial_id", pd.Series(dtype=object))):
        trial_src = None
        for nm in ["trial_id", "TRIAL_ID", "source_trial_id", "nct_id", "NCT_ID", "trial", "TRIAL"]:
            trial_src = _find_ci(df, nm)
            if trial_src:
                df["trial_id"] = df[trial_src]
                break
        if trial_src is None:
            df["trial_id"] = "TRIAL_UNKNOWN"

    # 7.6) age backfill (from aliases or derive from DOB)
    if "age" not in df.columns or _all_na(df.get("age", pd.Series(dtype=object))):
        # (a) Copy from common aliases if present
        alias = None
        for nm in ["age", "AGE", "Age", "age_years", "age_yrs", "AGE_YEARS"]:
            alias = _find_ci(df, nm)
            if alias:
                df["age"] = pd.to_numeric(df[alias], errors="coerce")
                break

        # (b) Derive from DOB if still missing
        if "age" not in df.columns or _all_na(df["age"]):
            dob_col = None
            for nm in ["DOB", "dob", "Dob", "date_of_birth", "birth_date", "BIRTH_DATE"]:
                dob_col = _find_ci(df, nm)
                if dob_col:
                    break
            if dob_col:
                env = _build_eval_env()
                years_between = env.get("years_between")
                if callable(years_between):
                    try:
                        sig = inspect.signature(years_between)
                        params = list(sig.parameters.values())
                        if len(params) == 1:
                            # years_between(dob)
                            df["age"] = df[dob_col].apply(lambda v: years_between(v))
                        else:
                            # years_between(dob, today)
                            today = datetime.now(timezone.utc).date().isoformat()
                            df["age"] = df[dob_col].apply(lambda v: years_between(v, today))
                    except Exception:
                        # If anything goes wrong, leave age as NaN
                        df["age"] = pd.to_numeric(df.get("age", pd.Series(index=df.index)), errors="coerce")

    # 8) Contacted & Consented (robust derivation)
    contact = None
    for nm in ["CONTACTED", "CONTACTED_FLAG", "CONTACTED_AT", "ContactedAt", "contacted_at",
               "CONTACTED_DATETIME", "CONTACT_DATE", "contacted"]:
        s = _flag_from_column(df, nm)
        if s is not None:
            contact = s.astype(int)
            break
    df["contacted"] = (df["contacted"].map(_as_int_flag).astype(int) if _find_ci(df, "contacted") else 0) \
                      if contact is None else contact

    consent = None
    for nm in ["CONSENTED", "CONSENTED_FLAG", "CONSENTED_AT", "ConsentedAt", "consented_at",
               "CONSENT_STATUS", "CONSENT", "CONSENT_DATE", "consented"]:
        s = _flag_from_column(df, nm)
        if s is not None:
            consent = s.astype(int)
            break
    df["consented"] = (df["consented"].map(_as_int_flag).astype(int) if _find_ci(df, "consented") else 0) \
                      if consent is None else consent

    # 9) Enrolled (needed by enrollment-rate metrics)
    enrolled = None
    for nm in [
        "ENROLLED", "ENROLLED_FLAG",
        "ENROLLED_AT", "EnrollDate", "ENROLL_DATE", "ENROLLMENT_DATE",
        "enrolled",
    ]:
        s = _flag_from_column(df, nm)
        if s is not None:
            enrolled = s.astype(int)
            break
    if enrolled is not None:
        df["enrolled"] = enrolled
    else:
        df["enrolled"] = (
            df["enrolled"].map(_as_int_flag).astype(int) if _find_ci(df, "enrolled") else 0
        )

    # 10) Reorder: canonical first, then the rest
    front = [
        "patient_id", "patient_id_hash", "patient_id_raw",
        *CanonicalCols, "contacted", "consented", "enrolled",
        "site_id", "trial_id", "age",
    ]
    front = [c for c in front if c in df.columns]
    df = df[front + [c for c in df.columns if c not in front]]

    return df
