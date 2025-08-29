from __future__ import annotations
from typing import Sequence
import pandas as pd


_REQUIRED_CANONICAL_V1: Sequence[str] = (
    "site_id",
    "trial_id",
    "patient_id",
    "race",
    "ethnicity",
    "sex",
    "eligible",
    "contacted",
    "consented",
)

def validate_canonical_v1(df: pd.DataFrame) -> None:
    """
    Minimal schema check used by tests. Raises ValueError on failure.
    """
    missing = [c for c in _REQUIRED_CANONICAL_V1 if c not in df.columns]
    if missing:
        raise ValueError(
            "Canonical v1 validation failed:\n"
            f"Missing required columns: {missing}"
        )
