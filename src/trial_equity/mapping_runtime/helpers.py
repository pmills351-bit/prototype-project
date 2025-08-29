# src/trial_equity/mapping_runtime/helpers.py
from __future__ import annotations

from typing import Any, Optional
import hashlib
from datetime import datetime, timezone, date
import math

import pandas as pd


# ---------------------------- public helpers (re-exported) ----------------------------

def parse_dt(v: Any) -> Optional[pd.Timestamp]:
    """
    Parse many datetime-like inputs into a pandas.Timestamp (UTC).
    Returns None for invalid/empty values.

    Accepts:
      - ISO strings (date or datetime)
      - pandas.Timestamp
      - datetime.datetime / datetime.date
      - numbers are treated as invalid (return None)
      - empty strings / NaNs -> None
    """
    if v is None:
        return None

    # Handle pandas NaN/NaT
    try:
        if pd.isna(v):
            return None
    except Exception:
        # If pd.isna fails (unusual), continue
        pass

    # datetime/date pass-through
    if isinstance(v, pd.Timestamp):
        # Ensure UTC
        return v.tz_convert("UTC") if v.tzinfo is not None else v.tz_localize("UTC")
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return pd.Timestamp(v)
    if isinstance(v, date):
        # Date only -> midnight UTC
        dt = datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
        return pd.Timestamp(dt)

    # Strings and other objects -> try pandas parser
    try:
        s = str(v).strip()
        if not s:
            return None
        ts = pd.to_datetime(s, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts)
    except Exception:
        return None


def years_between(a: Any, b: Any = None) -> Optional[float]:
    """
    Compute approximate whole years between two dates (a -> b).
    If b is None, uses "today" (UTC date). Returns None if inputs are invalid.

    - Accepts strings, datetime/date, or pd.Timestamp.
    - Uses a simple 365.25 day year conversion.
    """
    ta = parse_dt(a)
    if ta is None:
        return None

    if b is None:
        tb = pd.Timestamp(datetime.now(timezone.utc))
    else:
        tb = parse_dt(b)
        if tb is None:
            return None

    # Work on dates to avoid timezone noise
    da = ta.date()
    db = tb.date()
    delta_days = (db - da).days
    return delta_days / 365.25


def boolify(x: Any) -> int:
    """
    Convert common truthy/falsey representations to 0/1 integer flags.
    """
    if x is None:
        return 0

    # NaN/NaT -> 0
    try:
        if pd.isna(x):
            return 0
    except Exception:
        pass

    if isinstance(x, (int, float)):
        # Treat any non-zero numeric as true
        return 1 if (not isinstance(x, float) or not math.isnan(x)) and float(x) != 0.0 else 0

    s = str(x).strip().lower()
    if s in {"1", "true", "t", "y", "yes", "on"}:
        return 1
    if s in {"0", "false", "f", "n", "no", "off"}:
        return 0

    # non-empty strings default to true
    return 1 if s else 0


def hash_id(val: Any, salt: str = "") -> str:
    """
    Stable short SHA-256 hash for IDs (12 hex chars), salted.
    """
    return hashlib.sha256(f"{val}|{salt}".encode("utf-8")).hexdigest()[:12]
