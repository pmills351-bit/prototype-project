# te_engine.py — pure logic (no Streamlit)
import hashlib, uuid, datetime
from typing import Dict, Any, Iterable, Tuple
import pandas as pd
from dateutil import parser as dtparser

# ---------- Normalizers ----------
def _clean(x):
    if x is None: return ""
    return str(x).strip().lower()

def normalize_race(value: str) -> str:
    v = _clean(value)
    if v in ("", "unknown", "unk"): return "Unknown"
    if v in ("declined", "refused"): return "Declined"
    opts = {
        "white": "White",
        "black": "Black or African American",
        "african american": "Black or African American",
        "aa": "Black or African American",
        "asian": "Asian",
        "american indian": "American Indian or Alaska Native",
        "alaska native": "American Indian or Alaska Native",
        "native hawaiian": "Native Hawaiian or Other Pacific Islander",
        "pacific islander": "Native Hawaiian or Other Pacific Islander",
        "two or more": "Multiple",
        "multiracial": "Multiple",
        "multiple": "Multiple",
    }
    for k, out in opts.items():
        if k in v: return out
    return "Unknown"

def normalize_eth(value: str) -> str:
    v = _clean(value)
    if v in ("", "unknown", "unk"):
        return "Unknown"
    if v in ("declined", "refused"):
        return "Declined"
    NEG = {
        "not hispanic",
        "non-hispanic",
        "not latino",
        "non latino",
        "not hispanic or latino",
        "not of hispanic origin",
    }
    if any(n in v for n in NEG):
        return "Not Hispanic or Latino"
    if "hispanic" in v or "latino" in v:
        return "Hispanic or Latino"
    return "Unknown"

def normalize_sex(value: str) -> str:
    v = _clean(value)
    if v in ("", "unknown", "unk"): return "Unknown"
    if v in ("declined", "refused"): return "Declined"
    if v in ("female", "f"): return "Female"
    if v in ("male", "m"): return "Male"
    if "intersex" in v: return "Intersex"
    return "Unknown"

# ---------- Privacy & parsing ----------
def hash_id(salt: str, value: str) -> str:
    if value is None: value = ""
    import hashlib
    h = hashlib.sha256()
    h.update((salt + str(value)).encode("utf-8"))
    return h.hexdigest()

def parse_dt(x):
    if x is None or (isinstance(x, float) and pd.isna(x)): return None
    if isinstance(x, (datetime.datetime, datetime.date)): return x
    try:
        return dtparser.parse(str(x))
    except Exception:
        return None

def years_between(birth_date, ref_date):
    bd = parse_dt(birth_date)
    rd = parse_dt(ref_date)
    if bd is None or rd is None: return None
    y = rd.year - bd.year - ((rd.month, rd.day) < (bd.month, bd.day))
    return max(y, 0)

# ---------- Mapping runtime ----------
ALLOWED_FUNCS = {
    "normalize_race": normalize_race,
    "normalize_eth": normalize_eth,
    "normalize_sex": normalize_sex,
    "hash": hash_id,
    "parse_dt": parse_dt,
    "years_between": years_between,
    "bool": bool,
    "int": int,
    "float": float,
    "str": str,
}

def _safe_eval(expr: str, row: Dict[str, Any], vars: Dict[str, Any]) -> Any:
    env = {"__builtins__": {}}
    env.update(ALLOWED_FUNCS)
    env.update(vars)
    env["row"] = row
    return eval(expr, env, {})

def apply_mapping(df: pd.DataFrame, mapping: Dict[str, Any], default_site_salt: str = "SITE_SALT") -> pd.DataFrame:
    import datetime, uuid
    assign = mapping.get("assign", {}) or {}
    cols_map = mapping.get("columns", {}) or {}
    prov = mapping.get("provenance", {}) or {}
    schema_version = mapping.get("schema_version", "1.0.0")
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    batch_id = str(uuid.uuid4())
    vars = {"SALT": default_site_salt, "load_time": now}

    out_rows = []
    for _, r in df.iterrows():
        row = r.to_dict()
        out = {}
        for k, v in assign.items():
            out[k] = v
        for k, expr in cols_map.items():
            val = None
            if isinstance(expr, str):
                try:
                    val = _safe_eval(expr, row, vars)
                except Exception:
                    val = row.get(expr, None)
            out[k] = val
        out["source_system"] = prov.get("source_system", "unknown")
        out["schema_version"] = schema_version
        out["ingested_at"] = now.isoformat()
        out["load_batch_id"] = batch_id
        out_rows.append(out)
    return pd.DataFrame(out_rows)

# ---------- Validation ----------
RACE = [
    "White","Black or African American","Asian",
    "American Indian or Alaska Native","Native Hawaiian or Other Pacific Islander",
    "Multiple","Unknown","Declined",
]
ETHN = ["Hispanic or Latino","Not Hispanic or Latino","Unknown","Declined"]
SEX  = ["Female","Male","Intersex","Unknown","Declined"]

REQUIRED = ["patient_id","site_id","trial_id","race","ethnicity","sex","age","eligible","selected"]

def validate_canonical_v1_inline(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing: raise ValueError(f"Missing required columns: {missing}")
    if not set(df["race"].dropna()).issubset(RACE): raise ValueError("Bad race values")
    if not set(df["ethnicity"].dropna()).issubset(ETHN): raise ValueError("Bad ethnicity values")
    if not set(df["sex"].dropna()).issubset(SEX): raise ValueError("Bad sex values")
    for col in ["eligible","selected"]:
        if not set(pd.to_numeric(df[col], errors="coerce").dropna().unique()).issubset({0,1}):
            raise ValueError(f"{col} must be 0/1")
    if "age" in df.columns and (pd.to_numeric(df["age"], errors="coerce") < 0).any():
        raise ValueError("Age must be >= 0")

