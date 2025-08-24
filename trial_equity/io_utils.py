import pandas as pd
from datetime import datetime, date
from dateutil import parser as dtparser
import hashlib

def parse_dt(x):
    """Best-effort parse of timestamps like '2025-08-01T10:00:00Z' or Excel dates."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (datetime, date)):
        return x
    try:
        return dtparser.parse(str(x))
    except Exception:
        return None

def years_between(birth_date, ref_date):
    """Whole years between two dates (never negative)."""
    bd = parse_dt(birth_date)
    rd = parse_dt(ref_date)
    if bd is None or rd is None:
        return None
    y = rd.year - bd.year - ((rd.month, rd.day) < (bd.month, bd.day))
    return max(y, 0)

def hash_id(salt: str, value: str) -> str:
    """Stable SHA-256 hash for pseudonymous IDs."""
    if value is None:
        value = ""
    h = hashlib.sha256()
    h.update((salt + str(value)).encode("utf-8"))
    return h.hexdigest()
