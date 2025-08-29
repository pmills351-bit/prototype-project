from __future__ import annotations
import pandas as pd
from .metrics import group_rate_ci, risk_ratio_table


def selection_by_race(df: pd.DataFrame) -> pd.DataFrame:
    """
    Selection rate by race: numerator = contacted, denominator = eligible
    Returns canonical columns:
      race, n, denom, rate, ci_low, ci_high
    (plus n_denom and group for compatibility)
    """
    res = group_rate_ci(df=df, group_col="race", num_col="contacted", den_cond_col="eligible")
    # Ensure exact projection/order the tests expect
    cols = ["race", "n", "denom", "rate", "ci_low", "ci_high"]
    return res[cols].reset_index(drop=True)


def rr_selection_by_race(df: pd.DataFrame, ref_race: str | None = None) -> pd.DataFrame:
    """
    Risk ratio of selection rates by race vs ref group (first row if None).
    """
    rates = group_rate_ci(df=df, group_col="race", num_col="contacted", den_cond_col="eligible")
    table = risk_ratio_table(rates, group_col="race", numerator_col="n", den_cond_col="denom", ref_group=ref_race)
    return table
