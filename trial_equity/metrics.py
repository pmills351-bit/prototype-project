# trial_equity/metrics.py
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import norm

# ---------------- Wilson binomial CI ----------------
def wilson_ci(k: int, n: int, alpha: float = 0.05):
    if n <= 0:
        return (np.nan, np.nan)
    z = norm.ppf(1 - alpha / 2)
    phat = k / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = (z * np.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n)) / denom
    return (center - margin, center + margin)

# ---------------- Rates by group with Wilson CI ----------------
def group_rate_ci(df: pd.DataFrame, group_col: str, num_col: str, den_cond_col: str, alpha: float = 0.05) -> pd.DataFrame:
    df = df.copy()
    df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0).astype(int)
    df[den_cond_col] = pd.to_numeric(df[den_cond_col], errors="coerce").fillna(0).astype(int)

    records = []
    for g, gdf in df.groupby(group_col, dropna=False):
        denom = int((gdf[den_cond_col] == 1).sum())
        num = int(((gdf[num_col] == 1) & (gdf[den_cond_col] == 1)).sum())
        rate = num / denom if denom > 0 else np.nan
        lo, hi = wilson_ci(num, denom, alpha=alpha) if denom > 0 else (np.nan, np.nan)
        records.append({group_col: g, "n_denom": denom, "n_num": num, "rate": rate, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(records)

# ---------------- Risk Ratio (Katz log method) ----------------
def katz_log_ci_rr(k1: int, n1: int, k0: int, n0: int, alpha: float = 0.05):
    """
    Katz log CI for RR. We return the CI; the caller should compute the raw RR (un-corrected).
    Apply Haldane-Anscombe (add 0.5) ONLY when any cell is zero to avoid infinite/undefined CI.
    """
    z = norm.ppf(1 - alpha / 2)

    # if any cell is zero, use continuity correction for CI
    any_zero = (k1 == 0) or (n1 - k1 == 0) or (k0 == 0) or (n0 - k0 == 0)
    if any_zero:
        k1c, n1c = k1 + 0.5, n1 + 1
        k0c, n0c = k0 + 0.5, n0 + 1
    else:
        k1c, n1c = k1, n1
        k0c, n0c = k0, n0

    # guard
    if n1c == 0 or n0c == 0:
        return (np.nan, np.nan)

    p1 = k1c / n1c
    p0 = k0c / n0c
    if p0 == 0:
        return (np.nan, np.nan)

    # standard error on log scale
    # (classic Katz: se = sqrt( (1-k1)/k1 + (1-k0)/k0 ) but in terms of proportions/continuity)
    if k1c == 0 or k0c == 0:
        return (np.nan, np.nan)
    se = np.sqrt((1 - p1) / k1c + (1 - p0) / k0c)

    # caller will pass raw rr; we only return CI bounds multiplier around rr
    llog = - z * se
    hlog = + z * se
    return (llog, hlog)

def group_rr(
    df: pd.DataFrame,
    group_col: str,
    num_col: str,
    den_cond_col: str,
    ref_value,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """
    Risk Ratio by group vs a reference group.
    RR point estimate uses RAW rates (no correction).
    CI uses Katz with continuity correction only when any 2x2 cell is zero.
    """
    rates = group_rate_ci(df, group_col=group_col, num_col=num_col, den_cond_col=den_cond_col, alpha=alpha)

    # find reference counts
    ref_row = rates[rates[group_col] == ref_value]
    if ref_row.empty:
        low = rates[group_col].astype(str).str.lower() == str(ref_value).lower()
        ref_row = rates[low]
    if ref_row.empty:
        raise ValueError(f"Reference group '{ref_value}' not found in column '{group_col}'")

    k0 = int(ref_row.iloc[0]["n_num"])
    n0 = int(ref_row.iloc[0]["n_denom"])
    r0 = (k0 / n0) if n0 > 0 else np.nan

    out = []
    for _, r in rates.iterrows():
        g = r[group_col]
        k1 = int(r["n_num"])
        n1 = int(r["n_denom"])
        r1 = (k1 / n1) if n1 > 0 else np.nan

        # point estimate: raw ratio
        rr = (r1 / r0) if (np.isfinite(r1) and np.isfinite(r0) and r0 > 0) else np.nan

        # CI: use Katz; get log-interval and exponentiate around rr
        if np.isfinite(rr):
            logs = katz_log_ci_rr(k1, n1, k0, n0, alpha=alpha)
            if not any(np.isnan(logs)):
                llog, hlog = logs
                rr_low, rr_high = (rr * np.exp(llog), rr * np.exp(hlog))
            else:
                rr_low, rr_high = (np.nan, np.nan)
        else:
            rr_low, rr_high = (np.nan, np.nan)

        out.append({
            group_col: g,
            "n_num": k1, "n_denom": n1, "rate": r["rate"],
            "rr": rr, "rr_low": rr_low, "rr_high": rr_high,
            "ref_group": ref_value
        })
    return pd.DataFrame(out)

