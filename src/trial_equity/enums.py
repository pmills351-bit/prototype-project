# Compatibility shim so tests can import:
#   from trial_equity.enums import normalize_race, normalize_eth, normalize_sex

from .normalize import (
    normalize_race,
    normalize_eth,
    normalize_sex,
)

__all__ = ["normalize_race", "normalize_eth", "normalize_sex"]
