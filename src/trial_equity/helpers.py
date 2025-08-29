from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable, Optional

import pandas as pd


# ---------------------------
# Datetime helpers
# ---------------------------

def parse_dt(x: Any) -> pd.Timestamp:
    """
    Parse *x* into a tz-aware UTC pandas Timestamp.

    - Strings / datetime-like / Timestamp are accepted
    - Naive timestamps are assumed to be UTC
    - Tz-aware timestamps are converted to UTC
    - Invalid inputs -> NaT
    """
    if isinstance(x, pd.Timestamp):
        ts = x
    else:
        ts = pd.to_datetime(x, utc=None, errors="coerce")

    if ts is pd.NaT:
        return ts

    # If timezone-naive: treat as UTC. If tz-aware: convert to UTC.
    if getattr(ts, "tzinfo", None) is None:
        return ts.tz_localize("UTC")
    else:
        return ts.tz_convert("UTC")


def years_between(a: Any, b: Optional[Any] = None) -> float:
    """
    Fractional years between a and b (b defaults to 'now' UTC).
    Uses 365.2425 day year to approximate.
    """
    ta = parse_dt(a)
    tb = parse_dt(b) if b is not None else pd.Timestamp.utcnow().tz_localize("UTC")

    if ta is pd.NaT or tb is pd.NaT:
        return float("nan")

    delta_days = (tb - ta).total_seconds() / (24 * 3600)
    return float(delta_days / 365.2425)


# ---------------------------
# Boolean / hashing helpers
# ---------------------------

_TRUE_STRS = {"1", "t", "true", "y", "yes"}
_FALSE_STRS = {"0", "f", "false", "n", "no"}

def boolify(x: Any) -> bool:
    """
    Coerce common truthy/falsey strings & numbers to bool.
    None/NaN -> False.
    Non-zero numbers -> True.
    """
    if x is None:
        return False
    if isinstance(x, (bool,)):
        return bool(x)
    if isinstance(x, (int, float)):
        try:
            return bool(int(x))
        except Exception:
            return bool(x)
    s = str(x).strip().lower()
    if s in _TRUE_STRS:
        return True
    if s in _FALSE_STRS:
        return False
    # Fallback: non-empty string => True
    return len(s) > 0


def hash_id(salt: Any, *parts: Any, length: int = 12) -> str:
    """
    Stable salted ID generator (hex prefix), default 12 characters.

    Uses BLAKE2b keyed hashing so different salts yield different ids.
    """
    key = str(salt).encode("utf-8")
    h = hashlib.blake2b(digest_size=16, key=key)
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x1f")  # field separator
    return h.hexdigest()[:length]


__all__ = [
    "parse_dt",
    "years_between",
    "boolify",
    "hash_id",
]
