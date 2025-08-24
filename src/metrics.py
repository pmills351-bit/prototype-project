# src/metrics.py
from __future__ import annotations
from typing import Iterable, Tuple
import numpy as np
import pandas as pd
from math import sqrt
rng = np.random.default_rng

# -----------------------------
# Core helpers
# -----------------------------
def wilson_ci(k: int, n: int, alpha: float = 0.05) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (np.nan, np.nan)
    z = 1.959963984540054 if alpha == 0.05 else _z_from_alpha(alpha)
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    lo, hi = center - half, center + half
    return (max(0.0, lo), min(1.0, hi))

def _z_from_alpha(alpha: float) -> float:
    # simple approximation for general alpha (not used by default)
    from math import erf, sqrt
    # inverse of Phi using approximation (for completeness)
    p = 1 - alpha/2
    # Abramowitz-Stegun approx
    a1,a2,a3 = -39.696830, 220.946098, -275.928510
    a4,a5,a6 = 138.357751, -30.664798, 2.506628
    b1,b2,b3 = -54.476098, 161.585836, -155.698979
    b4,b5,b6 = 66.801311, -13.280681, 0.0
    c1,c2,c3 = -0.007784894, -0.322396, -2.400758
    c4,c5,c6 = -2.549732, 4.374664, 2.938163
    d1,d2,d3 = 0.007784695, 0.322467, 2.445134
    d4,d5,d6 = 3.754408, 0.0, 0.0
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = sqrt(-2* np.log(p))
        x = (((((c1*q+c2)*q+c3)*q+c4)*q+c5)*q+c6)/((((d1*q+d2)*q+d3)*q+d4)*q+1)
    elif p <= phigh:
        q = p - 0.5
        r = q*q
        x = (((((a1*r+a2)*r+a3)*r+a4)*r+a5)*r+a6)*q/(((((b1*r+b2)*r+b3)*r+b4)*r+b5)*r+1)
    else:
        q = sqrt(-2* np.log(1-p))
        x = -(((((c1*q+c2)*q+c3)*q+c4)*q+c5)*q+c6)/((((d1*q+d2)*q+d3)*q+d4)*q+1)
    return float(x)

def rate_and_ci(y: Iterable[float], alpha: float = 0.05) -> Tuple[float, Tuple[float, float]]:
    y = pd.Series(y).dropna().astype(float)
    n = int(y.shape[0])
    k = int(y.sum())
    if n == 0:
        return (np.nan, (np.nan, np.nan))
    lo, hi = wilson_ci(k, n, alpha=alpha)
    return (k / n, (lo, hi))

# -----------------------------
# Bootstrap CIs for ratios/diffs
# -----------------------------
def _safe_div(a: np.ndarray, b: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    return a / np.clip(b, eps, None)

def _sim_p(n: int, p: float, B: int, rng_: np.random.Generator) -> np.ndarray:
    if not np.isfinite(p) or n <= 0:
        return np.full(B, np.nan, dtype=float)
    k = rng_.binomial(n, min(max(p, 0.0), 1.0), size=B)
    return k / np.maximum(n, 1)

def disparity_bootstrap_ci(p_g: float, p_ref: float, n_g: int, n_ref: int, B: int = 2000, seed: int = 42, alpha: float = 0.05) -> Tuple[float, Tuple[float, float]]:
    """Relative risk (ratio) via parametric bootstrap."""
    rr = p_g / p_ref if (np.isfinite(p_g) and np.isfinite(p_ref) and p_ref > 0) else np.nan
    r = np.random.default_rng(seed)
    ps_g = _sim_p(n_g, p_g, B, r)
    ps_r = _sim_p(n_ref, p_ref, B, r)
    sims = _safe_div(ps_g, ps_r)
    lo, hi = np.nanpercentile(sims, [100*alpha/2, 100*(1-alpha/2)])
    return rr, (float(lo), float(hi))

def risk_difference_bootstrap_ci(p_g: float, p_ref: float, n_g: int, n_ref: int, B: int = 2000, seed: int = 42, alpha: float = 0.05) -> Tuple[float, Tuple[float, float]]:
    """Risk difference (p_g - p_ref) via parametric bootstrap."""
    rd = p_g - p_ref if (np.isfinite(p_g) and np.isfinite(p_ref)) else np.nan
    r = np.random.default_rng(seed + 13)
    ps_g = _sim_p(n_g, p_g, B, r)
    ps_r = _sim_p(n_ref, p_ref, B, r)
    sims = ps_g - ps_r
    lo, hi = np.nanpercentile(sims, [100*alpha/2, 100*(1-alpha/2)])
    return rd, (float(lo), float(hi))

def relative_risk_bootstrap_ci(p_g: float, p_ref: float, n_g: int, n_ref: int, B: int = 2000, seed: int = 42, alpha: float = 0.05) -> Tuple[float, Tuple[float, float]]:
    """Alias of disparity (relative risk)."""
    return disparity_bootstrap_ci(p_g, p_ref, n_g, n_ref, B=B, seed=seed, alpha=alpha)

def parity_difference_bootstrap_ci(p_g: float, p_ref: float, n_g: int, n_ref: int, B: int = 2000, seed: int = 42, alpha: float = 0.05) -> Tuple[float, Tuple[float, float]]:
    """Parity difference defined as (p_ref - p_g)."""
    rd, (lo, hi) = risk_difference_bootstrap_ci(p_g, p_ref, n_g, n_ref, B=B, seed=seed, alpha=alpha)
    pdiff = -rd
    return pdiff, (-hi, -lo)

# -----------------------------
# Calibration helpers
# -----------------------------
def brier_score(y_true: Iterable[float], p_pred: Iterable[float]) -> float:
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(p_pred), dtype=float)
    if y.size == 0 or p.size == 0 or y.size != p.size:
        return np.nan
    if np.any(~np.isfinite(y)) or np.any(~np.isfinite(p)):
        return np.nan
    return float(np.mean((p - y) ** 2))

def reliability_table(y_true: Iterable[float], p_pred: Iterable[float], bins: int = 10, strategy: str = "quantile") -> pd.DataFrame:
    y = pd.Series(y_true, dtype=float)
    p = pd.Series(p_pred, dtype=float)
    ok = y.notna() & p.notna()
    y = y[ok]; p = p[ok]
    if y.empty:
        return pd.DataFrame(columns=["bin", "n", "p_mean", "y_rate"])
    if strategy == "quantile":
        q = pd.qcut(p, q=bins, duplicates="drop")
    else:
        q = pd.cut(p, bins=bins)
    g = pd.DataFrame({"y": y, "p": p, "bin": q}).groupby("bin", dropna=False)
    out = g.agg(n=("y", "size"), p_mean=("p", "mean"), y_rate=("y", "mean")).reset_index()
    return out

