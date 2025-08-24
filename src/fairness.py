# src/fairness.py
from __future__ import annotations
from typing import List, Optional, Sequence
import numpy as np
import pandas as pd

from .metrics import (
    rate_and_ci,
    disparity_bootstrap_ci,
    risk_difference_bootstrap_ci,
    relative_risk_bootstrap_ci,
    parity_difference_bootstrap_ci,
)

def parity_flag(d: float, lo: float, hi: float, lower: float = 0.8, upper: float = 1.25) -> str:
    """Strict CI-based parity flag."""
    if not (np.isfinite(d) and np.isfinite(lo) and np.isfinite(hi)):
        return "N/A"
    if hi < lower or lo > upper:
        return "Fail"
    if lo < lower or hi > upper:
        return "Borderline"
    return "Pass"

def _compute_group_rates(df: pd.DataFrame, group_cols: Sequence[str], outcome_col: str) -> pd.DataFrame:
    work = df.dropna(subset=list(group_cols) + [outcome_col]).copy()
    work[outcome_col] = work[outcome_col].astype(float)
    rows: List[dict] = []
    for keys, g in work.groupby(list(group_cols), dropna=False):
        keys = (keys,) if not isinstance(keys, tuple) else keys
        label = ";".join([str(k) for k in keys])
        n = int(g.shape[0])
        successes = int(g[outcome_col].sum())
        rate, (r_lo, r_hi) = rate_and_ci(g[outcome_col])
        rows.append({
            **{col: keys[i] for i, col in enumerate(group_cols)},
            "label": label,
            "n": n,
            "successes": successes,
            "selection_rate": float(rate) if np.isfinite(rate) else np.nan,
            "rate_ci_low": float(r_lo) if np.isfinite(r_lo) else np.nan,
            "rate_ci_high": float(r_hi) if np.isfinite(r_hi) else np.nan,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("n", ascending=False, kind="mergesort").reset_index(drop=True)

def _pick_reference(group_df: pd.DataFrame, strategy: str, custom_ref_value: Optional[str], group_cols: Sequence[str]) -> pd.Series:
    if group_df.empty:
        raise ValueError("No groups available to pick a reference.")
    if strategy == "largest_n":
        return group_df.sort_values(["n", "selection_rate"], ascending=[False, False]).iloc[0]
    if strategy == "max_rate":
        return group_df.sort_values("selection_rate", ascending=False).iloc[0]
    if strategy == "min_rate":
        return group_df.sort_values("selection_rate", ascending=True).iloc[0]
    if strategy == "custom":
        if len(group_cols) != 1:
            raise ValueError("Custom reference requires exactly one group column.")
        if custom_ref_value is None:
            raise ValueError("custom_ref_value must be provided when strategy='custom'.")
        hit = group_df[group_df[group_cols[0]].astype(str) == str(custom_ref_value)]
        if hit.empty:
            raise ValueError(f"Reference value '{custom_ref_value}' not found in column '{group_cols[0]}'.")
        return hit.iloc[0]
    raise ValueError(f"Unknown ref strategy: {strategy}")

def summarize_fairness(
    df: pd.DataFrame,
    group_cols: Sequence[str],
    outcome_col: str,
    ref_strategy: str = "largest_n",
    custom_ref_value: Optional[str] = None,
    lower: float = 0.8,
    upper: float = 1.25,
    B: int = 2000,
    seed: int = 42,
    use_point_fallback: bool = False,
    wide_ci_threshold: float = 0.5,
    lenient_parity: bool = False,   # NEW: Pass if point estimate within thresholds
) -> pd.DataFrame:
    """Compute per-group metrics and disparities vs a reference.

    Returns columns:
      group cols..., label, n, successes,
      selection_rate, rate_ci_low, rate_ci_high,
      disparity, disparity_ci_low, disparity_ci_high, parity_flag, is_reference,
      risk_diff, risk_diff_ci_low, risk_diff_ci_high,
      rel_risk, rel_risk_ci_low, rel_risk_ci_high,
      parity_diff, parity_diff_ci_low, parity_diff_ci_high
    """
    group_cols = list(group_cols)
    groups = _compute_group_rates(df, group_cols, outcome_col)
    if groups.empty:
        return pd.DataFrame(columns=[
            *group_cols, "label", "n", "successes",
            "selection_rate", "rate_ci_low", "rate_ci_high",
            "disparity", "disparity_ci_low", "disparity_ci_high",
            "parity_flag", "is_reference",
            "risk_diff", "risk_diff_ci_low", "risk_diff_ci_high",
            "rel_risk", "rel_risk_ci_low", "rel_risk_ci_high",
            "parity_diff", "parity_diff_ci_low", "parity_diff_ci_high",
        ])

    ref_row = _pick_reference(groups, ref_strategy, custom_ref_value, group_cols)
    p_ref = float(ref_row["selection_rate"]) if np.isfinite(ref_row["selection_rate"]) else np.nan
    n_ref = int(ref_row["n"]) if np.isfinite(ref_row["n"]) else 0

    disp_list, rd_list, rr_list, pdiff_list = [], [], [], []
    for _, row in groups.iterrows():
        p_g = float(row["selection_rate"]) if np.isfinite(row["selection_rate"]) else np.nan
        n_g = int(row["n"]) if np.isfinite(row["n"]) else 0

        disp, (d_lo, d_hi) = disparity_bootstrap_ci(p_g, p_ref, n_g, n_ref, B=B, seed=seed)
        rd, (rd_lo, rd_hi) = risk_difference_bootstrap_ci(p_g, p_ref, n_g, n_ref, B=B, seed=seed)
        rr, (rr_lo, rr_hi) = relative_risk_bootstrap_ci(p_g, p_ref, n_g, n_ref, B=B, seed=seed)
        pdiff, (pd_lo, pd_hi) = parity_difference_bootstrap_ci(p_g, p_ref, n_g, n_ref, B=B, seed=seed)

        # ---- Parity logic (strict default; lenient optional) ----
        if lenient_parity and np.isfinite(disp):
            if lower <= disp <= upper:
                flag = "Pass"
            else:
                flag = parity_flag(disp, d_lo, d_hi, lower=lower, upper=upper)
        else:
            flag = parity_flag(disp, d_lo, d_hi, lower=lower, upper=upper)
            if flag == "Borderline" and use_point_fallback and np.isfinite(disp):
                if (d_hi - d_lo) > wide_ci_threshold and (disp < lower or disp > upper):
                    flag = "Fail"
        # ---------------------------------------------------------

        disp_list.append((disp, d_lo, d_hi, flag))
        rd_list.append((rd, rd_lo, rd_hi))
        rr_list.append((rr, rr_lo, rr_hi))
        pdiff_list.append((pdiff, pd_lo, pd_hi))

    groups["disparity"] = [x[0] for x in disp_list]
    groups["disparity_ci_low"] = [x[1] for x in disp_list]
    groups["disparity_ci_high"] = [x[2] for x in disp_list]
    groups["parity_flag"] = [x[3] for x in disp_list]

    groups["risk_diff"] = [x[0] for x in rd_list]
    groups["risk_diff_ci_low"] = [x[1] for x in rd_list]
    groups["risk_diff_ci_high"] = [x[2] for x in rd_list]

    groups["rel_risk"] = [x[0] for x in rr_list]
    groups["rel_risk_ci_low"] = [x[1] for x in rr_list]
    groups["rel_risk_ci_high"] = [x[2] for x in rr_list]

    groups["parity_diff"] = [x[0] for x in pdiff_list]
    groups["parity_diff_ci_low"] = [x[1] for x in pdiff_list]
    groups["parity_diff_ci_high"] = [x[2] for x in pdiff_list]

    groups["is_reference"] = groups.index == ref_row.name
    groups = pd.concat([groups.loc[[ref_row.name]], groups.drop(index=ref_row.name)], axis=0).reset_index(drop=True)
    return groups

def format_group_table_for_display(result: pd.DataFrame, show_counts: bool = True) -> pd.DataFrame:
    """Pretty-print columns and choose a sane default subset for Streamlit."""
    if result.empty:
        return result.copy()

    disp = result.copy()
    disp["rate_ci"] = disp.apply(
        lambda r: f"{r.selection_rate:.3f} [{r.rate_ci_low:.3f}–{r.rate_ci_high:.3f}]" if np.isfinite(r.selection_rate) else "N/A",
        axis=1,
    )
    disp["disparity_ci"] = disp.apply(
        lambda r: f"{r.disparity:.3f} [{r.disparity_ci_low:.3f}–{r.disparity_ci_high:.3f}]" if np.isfinite(r.disparity) else "N/A",
        axis=1,
    )
    disp["risk_diff_ci"] = disp.apply(
        lambda r: f"{r.risk_diff:+.3f} [{r.risk_diff_ci_low:+.3f}–{r.risk_diff_ci_high:+.3f}]" if np.isfinite(r.risk_diff) else "N/A",
        axis=1,
    )
    disp["rel_risk_ci"] = disp.apply(
        lambda r: f"{r.rel_risk:.3f} [{r.rel_risk_ci_low:.3f}–{r.rel_risk_ci_high:.3f}]" if np.isfinite(r.rel_risk) else "N/A",
        axis=1,
    )
    disp["parity_diff_ci"] = disp.apply(
        lambda r: f"{r.parity_diff:+.3f} [{r.parity_diff_ci_low:+.3f}–{r.parity_diff_ci_high:+.3f}]" if np.isfinite(r.parity_diff) else "N/A",
        axis=1,
    )

    metric_cols = {
        "label","n","successes","selection_rate","rate_ci_low","rate_ci_high",
        "disparity","disparity_ci_low","disparity_ci_high","parity_flag","is_reference",
        "risk_diff","risk_diff_ci_low","risk_diff_ci_high",
        "rel_risk","rel_risk_ci_low","rel_risk_ci_high",
        "parity_diff","parity_diff_ci_low","parity_diff_ci_high",
        "rate_ci","disparity_ci","risk_diff_ci","rel_risk_ci","parity_diff_ci",
    }
    group_only_cols = [c for c in disp.columns if c not in metric_cols]

    cols = group_only_cols + ["is_reference", "rate_ci", "disparity_ci", "parity_flag", "risk_diff_ci", "rel_risk_ci", "parity_diff_ci"]
    if show_counts:
        cols = group_only_cols + ["n", "successes", "is_reference", "rate_ci", "disparity_ci", "parity_flag", "risk_diff_ci", "rel_risk_ci", "parity_diff_ci"]

    out = disp[cols].rename(columns={
        "is_reference": "ref",
        "rate_ci": "selection rate [95% CI]",
        "disparity_ci": "disparity [95% CI]",
        "parity_flag": "parity",
        "risk_diff_ci": "risk difference [95% CI]",
        "rel_risk_ci": "relative risk [95% CI]",
        "parity_diff_ci": "parity difference (ref − grp) [95% CI]",
        "n": "n",
        "successes": "successes",
    })
    return out


