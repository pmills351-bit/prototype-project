# src/validation.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd

_OUTCOME_MAP = {
    "1": 1, "0": 0,
    "yes": 1, "no": 0,
    "true": 1, "false": 0,
    "y": 1, "n": 0,
    "t": 1, "f": 0,
}

def clean_and_validate(
    df: pd.DataFrame,
    group_cols: List[str],
    outcome_col: str,
    *,
    drop_na_rows: bool = True,
    missing_token: str = "〈missing〉",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    - Normalizes common encodings of the outcome to 0/1 (strings yes/no/true/false/1/0).
    - Optionally drops rows with NA in any selected group or the outcome.
    - Returns (clean_df, report) where report includes counts and distinct values for transparency.
    """
    rep: Dict[str, Any] = {
        "required_present": True,
        "missing_required": [],
        "coerced_outcome_count": 0,
        "nonbinary_outcome_after_coercion": 0,
        "dropped_missing_rows": 0,
        "distinct_values": {},
    }

    # Required columns check
    required = list(group_cols) + [outcome_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        rep["required_present"] = False
        rep["missing_required"] = missing
        return df.copy(), rep

    work = df.copy()

    # Outcome normalization to 0/1 where possible
    before_nonbinary = (~work[outcome_col].isin([0, 1])).sum() if outcome_col in work else 0
    s = work[outcome_col].astype(str).str.strip().str.lower()
    mapped = s.map(_OUTCOME_MAP)
    # Use mapped where available, else try numeric coercion
    coerced = pd.to_numeric(work[outcome_col], errors="coerce")
    work[outcome_col] = mapped.fillna(coerced)
    rep["coerced_outcome_count"] = int(before_nonbinary)

    # Count remaining non-binary (not 0/1) after coercion
    rep["nonbinary_outcome_after_coercion"] = int(
        (~work[outcome_col].isin([0, 1]) & work[outcome_col].notna()).sum()
    )

    # Fill missing tokens for category visibility (do not replace real NAs in outcome)
    for col in group_cols:
        if col in work.columns:
            work[col] = (
                work[col]
                .astype(str)
                .replace({"nan": missing_token})
                .fillna(missing_token)
            )

    # Distinct values per selected group column
    for col in group_cols:
        if col in work.columns:
            vals = sorted(pd.Series(work[col].astype(str).unique()).tolist())
            rep["distinct_values"][col] = vals

    # Optional: drop rows with NA in required cols (after mapping)
    if drop_na_rows:
        before = len(work)
        mask_required_ok = work[required].notna().all(axis=1)
        work = work[mask_required_ok]
        rep["dropped_missing_rows"] = int(before - len(work))

    return work, rep
