# src/trial_equity/mapping_runtime/env.py
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

import pandas as pd

# Optional: these exist in your codebase; if not, stub them gracefully.
try:
    from trial_equity.normalize import normalize_race, normalize_eth, normalize_sex
except Exception:  # pragma: no cover
    def normalize_race(x):  # type: ignore
        return x

    def normalize_eth(x):  # type: ignore
        return x

    def normalize_sex(x):  # type: ignore
        return x


# ---------------------------
# Safe builtins allowed in eval
# ---------------------------

SAFE_BUILTINS: Dict[str, Any] = {
    # Numeric & casting
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "len": len,
    "sum": sum,
    "any": any,
    "all": all,
}


# ---------------------------
# Date helpers
# ---------------------------

def parse_dt(x: Any) -> pd.Timestamp:
    """
    Parse *x* into a tz-aware UTC pandas Timestamp.
    - Strings / datetime-like / Timestamp are accepted
    - Naive timestamps are assumed to be UTC
    - tz-aware timestamps are tz-converted to UTC
    - Invalid inputs (including None) -> NaT
    """
    if isinstance(x, pd.Timestamp):
        ts = x
    else:
        # errors="coerce" returns NaT for invalid inputs (including None)
        ts = pd.to_datetime(x, utc=None, errors="coerce")

    if ts is pd.NaT:
        return ts

    # If timezone-naive: treat as UTC. If tz-aware: convert to UTC.
    tz = getattr(ts, "tzinfo", None)
    if tz is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def years_between(a: Any, b: Any | None = None) -> float:
    """
    Years between times a and b (default b = now UTC).
    Handles tz-aware or tz-naive inputs and None/invalid -> NaN.
    """
    ta = parse_dt(a)
    if pd.isna(ta):
        return float("nan")

    tb = parse_dt(b) if b is not None else pd.Timestamp.utcnow().tz_localize("UTC")
    if pd.isna(tb):
        return float("nan")

    delta = (tb - ta).total_seconds()
    # Average Gregorian year
    return delta / (365.2425 * 24 * 3600.0)


# ---------------------------
# Misc helpers exposed to mapping expressions
# ---------------------------

def boolify(x: Any) -> int:
    """
    Turn common truthy/falsey representations into 0/1 integers.
    """
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0
    if isinstance(x, (int, bool)):
        return int(bool(x))
    s = str(x).strip().lower()
    if s in {"y", "yes", "true", "t", "1"}:
        return 1
    if s in {"n", "no", "false", "f", "0", ""}:
        return 0
    # fallback: non-empty -> true
    return 1 if s else 0


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def safe_float(x: Any, default: float = float("nan")) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _hash_bytes(s: str) -> bytes:
    return hashlib.sha256(s.encode("utf-8")).digest()


def _to_base32(b: bytes) -> str:
    # Crockford-like base32 without padding, uppercase
    import base64

    return base64.b32encode(b).decode("ascii").rstrip("=").upper()


def hash_id(salt: str, *parts: Any, length: int = 12) -> str:
    """
    Deterministic, stable hashed ID, default 12 chars [A-Z2-7].
    Changing salt changes output (used by tests to check variation).
    """
    msg = salt + "|" + "|".join("" if p is None else str(p) for p in parts)
    b = _hash_bytes(msg)
    base = _to_base32(b)
    # Guarantee we have enough characters, but cap to reasonable max
    if length <= 0:
        length = 12
    return base[:length]


# Back-compat alias – some mapping YAML may call `hash(SALT, value)`
# We'll export `hash` as an alias to `hash_id`.
hash = hash_id  # noqa: A001 (shadow built-in intentionally for env alias)


# ---------------------------
# What we export into the eval environment
# ---------------------------

BASE_ENV_EXPORTS: Dict[str, Any] = {
    # builtins subset
    **SAFE_BUILTINS,
    # normalization helpers
    "normalize_race": normalize_race,
    "normalize_eth": normalize_eth,
    "normalize_sex": normalize_sex,
    # booleans / casting
    "boolify": boolify,
    "safe_int": safe_int,
    "safe_float": safe_float,
    # hashing
    "hash_id": hash_id,
    "hash": hash,  # alias
    # time helpers
    "parse_dt": parse_dt,
    "years_between": years_between,
    # pandas for occasional direct use (optional)
    "pd": pd,
}


def _build_eval_env(default_site_salt: str | None = None, extra_env: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Build the eval environment dictionary injected into mapping expressions.
    """
    env = dict(BASE_ENV_EXPORTS)
    # Common symbolic salt name accessible inside expressions
    env["SALT"] = default_site_salt or ""
    if extra_env:
        env.update(extra_env)
    return env
