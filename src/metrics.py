# src/metrics.py
from __future__ import annotations
from typing import Tuple, Dict, Iterable, Optional
import math
import numpy as np
import pandas as pd

# ============================================================
# Core proportion + CI utilities
# ============================================================

def _z_from_alpha(alpha: float) -> float:
    """Two-sided z for (1 - alpha) CI. Falls back to 1.95996 if SciPy not available."""
    if not (0.0 < alpha < 1.0):
        alpha = 0.05
    try:
        from scipy.stats import norm  # type: ignore
        return float(norm.ppf(1 - alpha / 2.0))
    except Exception:
        return 1.959963984540054  # ≈ 95% CI


def rate_and_ci(successes: int, n: int, alpha: float = 0.05) -> Tuple[float, float, float]:
    """
    Wilson score interval for a binomial proportion.
    Returns (rate, lo, hi) clipped to [0,1]. If n<=0 -> (nan, nan, nan).
    """
    if n is None or n <= 0:
        return (float("nan"), float("nan"), float("nan"))

    p = successes / n
    z = _z_from_alpha(alpha)
    z2 = z * z

    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return (p, lo, hi)


# Back-compat aliases some codebases expect
wilson_rate_ci = rate_and_ci
selection_rate_ci = rate_and_ci


# ============================================================
# Disparity & bootstrap utilities
# ============================================================

def disparity_ratio(rate: float, ref_rate: float) -> float:
    """rate / ref_rate; returns nan if ref_rate<=0."""
    if ref_rate is None or ref_rate <= 0:
        return float("nan")
    return float(rate) / float(ref_rate)


def risk_difference(rate: float, ref_rate: float) -> float:
    """group - ref (in absolute points)."""
    if any(pd.isna([rate, ref_rate])):
        return float("nan")
    return float(rate) - float(ref_rate)


def parity_difference(ref_rate: float, rate: float) -> float:
    """ref - group (in absolute points)."""
    if any(pd.isna([rate, ref_rate])):
        return float("nan")
    return float(ref_rate) - float(rate)


def _binom_sample(successes: int, n: int, size: int, rng: np.random.Generator) -> np.ndarray:
    """Sample counts ~ Binomial(n, p̂) for bootstrap."""
    if n <= 0:
        return np.full(size, np.nan)
    p = max(0.0, min(1.0, successes / n))
    return rng.binomial(n=n, p=p, size=size)


def bootstrap_disparity_ci(
    succ: int,
    n: int,
    ref_succ: int,
    ref_n: int,
    B: int = 1000,
    seed: int = 123,
    alpha: float = 0.05,
) -> Tuple[float, float]:
    """
    Non-parametric-esque (parametric binomial) bootstrap for disparity ratio.
    Returns (lo, hi) for group_rate / ref_rate using Wilson rate per draw to reduce 0/0 artifacts.
    """
    rng = np.random.default_rng(seed)
    if n <= 0 or ref_n <= 0:
        return (float("nan"), float("nan"))

    draws_g = _binom_sample(succ, n, B, rng)
    draws_r = _binom_sample(ref_succ, ref_n, B, rng)

    # Convert to rates with a small stabilizer via Wilson center (better small-n behavior)
    z = _z_from_alpha(alpha)
    z2 = z * z

    def _rate_from_count(k, N):
        if N <= 0:
            return np.nan
        p = k / N
        denom = 1.0 + z2 / N
        center = (p + z2 / (2.0 * N)) / denom
        return center

    rates_g = np.array([_rate_from_count(int(k), int(n)) for k in draws_g], dtype=float)
    rates_r = np.array([_rate_from_count(int(k), int(ref_n)) for k in draws_r], dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = rates_g / rates_r
    ratios = ratios[np.isfinite(ratios)]
    if ratios.size == 0:
        return (float("nan"), float("nan"))

    lo = float(np.quantile(ratios, alpha / 2.0))
    hi = float(np.quantile(ratios, 1 - alpha / 2.0))
    return (lo, hi)


# ============================================================
# Calibration metrics (optional in UI)
# ============================================================

def brier_score(y_true: Iterable[float], y_prob: Iterable[float]) -> float:
    """Mean squared error between true labels (0/1) and predicted probabilities [0,1]."""
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(y_prob), dtype=float)
    if y.size == 0 or p.size == 0 or y.size != p.size:
        return float("nan")
    # clip probs
    p = np.clip(p, 0.0, 1.0)
    return float(np.mean((p - y) ** 2))


def reliability_table(
    y_true: Iterable[float],
    y_prob: Iterable[float],
    bins: int = 10,
    strategy: str = "quantile",
) -> pd.DataFrame:
    """
    Returns a table with columns: [bin, p_mean, y_rate, n].
    strategy ∈ {"uniform","quantile"}; quantile gives balanced counts per bin.
    """
    y = pd.Series(list(y_true), dtype=float)
    p = pd.Series(list(y_prob), dtype=float).clip(0.0, 1.0)

    if len(y) == 0 or len(p) == 0 or len(y) != len(p):
        return pd.DataFrame(columns=["bin", "p_mean", "y_rate", "n"])

    if strategy == "uniform":
        edges = np.linspace(0, 1, bins + 1)
        binned = pd.cut(p, bins=edges, include_lowest=True, duplicates="drop")
    else:  # quantile
        try:
            binned = pd.qcut(p, q=bins, duplicates="drop")
        except ValueError:
            # Not enough unique probabilities
            return pd.DataFrame(columns=["bin", "p_mean", "y_rate", "n"])

    df = pd.DataFrame({"bin": binned, "p": p, "y": y})
    agg = (
        df.dropna(subset=["bin"])
          .groupby("bin", observed=True)
          .agg(p_mean=("p", "mean"), y_rate=("y", "mean"), n=("y", "size"))
          .reset_index()
    )
    return agg
