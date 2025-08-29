"""
Lightweight statistical utilities (Wilson CI).
"""
from __future__ import annotations
from math import sqrt
from typing import Tuple

def wilson_ci(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion (two-sided)."""
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = p + z2 / (2*n)
    adj = z * sqrt((p*(1-p) + z2/(4*n)) / n)
    lower = max(0.0, (center - adj) / denom)
    upper = min(1.0, (center + adj) / denom)
    return (lower, upper)
