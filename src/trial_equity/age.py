from __future__ import annotations

from typing import Any
import pandas as pd


def parse_dt(x: Any) -> pd.Timestamp:
    """
    Parse *x* into a tz-aware UTC pandas Timestamp.

    - Accepts strings / datetime-like / Timestamp.
    - Invalid inputs -> NaT.
    - Naive inputs are treated as UTC.
    - tz-aware inputs are converted to UTC (tz_convert).

    This implementation explicitly avoids the common error:
      "Cannot localize tz-aware Timestamp, use tz_convert for conversions"
    by branching on tz-awareness.
    """
    # Fast-path: already a Timestamp
    if isinstance(x, pd.Timestamp):
        ts = x
    else:
        # errors="coerce" -> invalid -> NaT
        ts = pd.to_datetime(x, utc=None, errors="coerce")

    if ts is pd.NaT:
        return ts

    # If timezone-naive: treat as UTC. If tz-aware: convert to UTC.
    tzinfo = getattr(ts, "tzinfo", None)
    if tzinfo is None:
        return ts.tz_localize("UTC")
    else:
        return ts.tz_convert("UTC")


def years_between(a: Any, b: Any | None = None) -> float:
    """
    Fractional years between datetimes a and b (default now).
    Returns NaN if either side cannot be parsed.

    Uses 365.25-day year to approximate leap years. Suitable for
    computing ages or elapsed years for metrics.
    """
    ta = parse_dt(a)
    tb = parse_dt(b if b is not None else pd.Timestamp.utcnow())
    if ta is pd.NaT or tb is pd.NaT:
        return float("nan")
    delta_days = (tb - ta).total_seconds() / 86400.0
    return delta_days / 365.25


__all__ = ["parse_dt", "years_between"]
