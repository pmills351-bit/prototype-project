# src/fairness.py
from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
import itertools
import numpy as np
import pandas as pd

from .metrics import (
    rate_and_ci,
    disparity_ratio,
    risk_difference,
    parity_difference,
    bootstrap_disparity_ci,
)

# ============================================================
# Helpers
# ============================================================

def _intersectional_key(row: pd.Series, cols: List[str]) -> Tuple:
    """Return a tuple representing the intersectional group."""
    return tuple(str(row[c]) if c in row and pd.notna(row[c]) else "〈missing〉" for c in cols)


def _choose_reference(
    table: pd.DataFrame,
    ref_strategy: str = "largest_n",
    custom_ref_value: Optional[str] = None,
) -> Tuple[str, float, int, int]:
    """
    Choose reference group and return (ref_label, ref_rate, ref_successes, ref_n).
    table must have columns: ['group','successes','n','rate'].
    """
    ref_strategy = (ref_strategy or "largest_n").lower()

    if ref_strategy == "custom" and custom_ref_value is not None:
        ref_row = table.loc[table["group"] == custom_ref_value]
        if not ref_row.empty:
            r = ref_row.iloc[0]
            return (str(r["group"]), float(r["rate"]), int(r["successes"]), int(r["n"]))

    if ref_strategy == "max_rate":
        r = table.sort_values(["rate", "n"], ascending=[False, False]).iloc[0]
    elif ref_strategy == "min_rate":
        r = table.sort_values(["rate", "n"], ascending=[True, False]).iloc[0]
    else:  # largest_n (default)
        r = table.sort_values(["n", "rate"], ascending=[False, False]).iloc[0]

    return (str(r["group"]), float(r["rate"]), int(r["successes"]), int(r["n"]))


# ============================================================
# Main API
# ============================================================

def summarize_fairness(
    df: pd.DataFrame,
    group_cols: List[str],
    outcome_col: str,
    ref_strategy: str = "largest_n",
    custom_ref_value: Optional[str] = None,
    lower: float = 0.8,
    upper: float = 1.25,
    B: int = 1000,
    seed: int = 123,
    use_point_fallback: bool = True,
    wide_ci_threshold: float = 0.5,
    lenient_parity: bool = False,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Compute per-group selection rates with Wilson CIs, disparity ratios with bootstrap CIs,
    and parity decisions vs [lower, upper]. Supports intersectional groups.

    Returns a dict with keys:
      - 'by_group': DataFrame of per-group metrics
      - 'ref': reference group label
      - 'thresholds': (lower, upper)
    """
    if df is None or df.empty:
        return {
            "by_group": pd.DataFrame(columns=[
                "group", "n", "successes", "rate", "rate_lo", "rate_hi",
                "disparity", "disp_lo", "disp_hi", "risk_diff", "parity_diff", "parity", "ref",
            ]),
            "ref": None,
            "thresholds": (lower, upper),
        }

    # Build intersectional label (or single col)
    gc = list(group_cols or [])
    if not gc:
        raise ValueError("group_cols must be a non-empty list.")

    work = df.copy()
    # Normalize outcome to int 0/1 if needed
    work[outcome_col] = pd.to_numeric(work[outcome_col], errors="coerce")
    work = work.dropna(subset=[outcome_col])
    work[outcome_col] = (work[outcome_col] > 0).astype(int)

    # Construct a "group" label string for display; keep separate columns too
    if len(gc) == 1:
        group_series = work[gc[0]].astype("string").fillna("〈missing〉")
    else:
        group_series = work.apply(lambda r: " × ".join(_intersectional_key(r, gc)), axis=1)

    tmp = pd.DataFrame({
        "group": group_series,
        "y": work[outcome_col].astype(int),
    })
    grouped = tmp.groupby("group", dropna=False, observed=True).agg(
        successes=("y", "sum"),
        n=("y", "size"),
    ).reset_index()

    # Rates + Wilson CI
    rates = grouped.apply(
        lambda r: rate_and_ci(int(r["successes"]), int(r["n"]), alpha=alpha), axis=1
    )
    grouped[["rate", "rate_lo", "rate_hi"]] = pd.DataFrame(rates.tolist(), index=grouped.index)

    # Choose reference
    ref_label, ref_rate, ref_succ, ref_n = _choose_reference(
        grouped.rename(columns={"group": "group", "successes": "successes", "n": "n", "rate": "rate"}),
        ref_strategy=ref_strategy,
        custom_ref_value=custom_ref_value,
    )
    grouped["ref"] = (grouped["group"] == ref_label)

    # Disparity (point) and CI via bootstrap
    disp_ci = grouped.apply(
        lambda r: bootstrap_disparity_ci(
            succ=int(r["successes"]),
            n=int(r["n"]),
            ref_succ=int(ref_succ),
            ref_n=int(ref_n),
            B=int(B),
            seed=int(seed),
            alpha=alpha,
        ),
        axis=1
    )
    grouped[["disp_lo", "disp_hi"]] = pd.DataFrame(disp_ci.tolist(), index=grouped.index)

    # Point disparity using rates (avoid div by zero handled in disparity_ratio)
    grouped["disparity"] = grouped.apply(lambda r: disparity_ratio(r["rate"], ref_rate), axis=1)

    # Risk & parity differences
    grouped["risk_diff"] = grouped.apply(lambda r: risk_difference(r["rate"], ref_rate), axis=1)
    grouped["parity_diff"] = grouped.apply(lambda r: parity_difference(ref_rate, r["rate"]), axis=1)

    # Parity decision
    def decide_parity(row) -> str:
        d = float(row["disparity"])
        lo = float(row["disp_lo"])
        hi = float(row["disp_hi"])

        # Lenient mode: Pass if point estimate is within thresholds
        if lenient_parity and (lower <= d <= upper):
            return "Pass"

        # Strict mode (CI-based)
        # Fail if CI entirely outside [lower, upper]:
        if hi < lower or lo > upper:
            return "Fail"

        # Borderline if CI overlaps thresholds
        borderline = (lo < lower < hi) or (lo < upper < hi) or (lower <= lo <= upper) or (lower <= hi <= upper)
        if borderline:
            # Optional fallback: if CI is very wide and point estimate is outside, call Fail
            if use_point_fallback and (hi - lo) >= float(wide_ci_threshold) and not (lower <= d <= upper):
                return "Fail"
            return "Borderline"

        # Otherwise Pass
        return "Pass"

    grouped["parity"] = grouped.apply(decide_parity, axis=1)

    # Ensure ref row shows "ref" marker in formatted table later
    return {
        "by_group": grouped[
            ["group", "n", "successes", "rate", "rate_lo", "rate_hi",
             "disparity", "disp_lo", "disp_hi", "risk_diff", "parity_diff", "parity", "ref"]
        ].copy(),
        "ref": ref_label,
        "thresholds": (lower, upper),
    }


# ============================================================
# Display formatting used by the Streamlit app
# ============================================================

def _fmt_ci(lo: float, hi: float, digits: int = 3) -> str:
    if pd.isna(lo) or pd.isna(hi):
        return "N/A"
    return f"[{lo:.{digits}f}, {hi:.{digits}f}]"


def _fmt_rate_ci(rate: float, lo: float, hi: float, digits: int = 3) -> str:
    if pd.isna(rate):
        return "N/A"
    return f"{rate:.{digits}f} {_fmt_ci(lo, hi, digits)}"


def format_group_table_for_display(result: Dict[str, Any], show_counts: bool = True) -> pd.DataFrame:
    """
    Convert summarize_fairness() output into the exact columns the UI expects:

      ['group','n','successes','ref',
       'selection rate [95% CI]',
       'disparity [95% CI]','parity',
       'risk difference [95% CI]',
       'relative risk [95% CI]',
       'parity difference (ref − grp) [95% CI]']

    - 'relative risk' equals disparity (included for completeness).
    """
    if result is None or "by_group" not in result or result["by_group"] is None:
        return pd.DataFrame(columns=[
            "group","n","successes","ref",
            "selection rate [95% CI]",
            "disparity [95% CI]","parity",
            "risk difference [95% CI]",
            "relative risk [95% CI]",
            "parity difference (ref − grp) [95% CI]",
        ])

    df = result["by_group"].copy()

    # Formatted columns
    rate_ci_col = df.apply(lambda r: _fmt_rate_ci(r["rate"], r["rate_lo"], r["rate_hi"]), axis=1)
    disp_ci_col = df.apply(lambda r: _fmt_rate_ci(r["disparity"], r["disp_lo"], r["disp_hi"]), axis=1)

    # Risk/Parity differences don't have natural multiplicative CI here; show point only
    risk_diff_col = df["risk_diff"].map(lambda x: "N/A" if pd.isna(x) else f"{x:.3f}")
    rel_risk_col = disp_ci_col  # same as disparity for display
    parity_diff_col = df["parity_diff"].map(lambda x: "N/A" if pd.isna(x) else f"{x:.3f}")

    out_cols = {
        "group": df["group"],
        "n": df["n"] if show_counts else pd.Series([None]*len(df)),
        "successes": df["successes"] if show_counts else pd.Series([None]*len(df)),
        "ref": df["ref"].map(lambda b: "ref" if bool(b) else ""),
        "selection rate [95% CI]": rate_ci_col,
        "disparity [95% CI]": disp_ci_col,
        "parity": df["parity"],
        "risk difference [95% CI]": risk_diff_col,
        "relative risk [95% CI]": rel_risk_col,
        "parity difference (ref − grp) [95% CI]": parity_diff_col,
    }

    display = pd.DataFrame(out_cols)

    # Sort: show reference first, then by group name
    display = pd.concat([
        display[display["ref"] == "ref"],
        display[display["ref"] != "ref"].sort_values("group", kind="stable")
    ], axis=0, ignore_index=True)

    return display
