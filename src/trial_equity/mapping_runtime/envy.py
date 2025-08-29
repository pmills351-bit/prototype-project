# src/trial_equity/mapping_runtime/envy.py
from __future__ import annotations
from typing import Any, Dict

from .helpers import parse_dt, years_between, boolify, hash_id
from ..normalize import normalize_race, normalize_eth, normalize_sex


def _build_eval_env(site_salt: str = "", **overrides: Any) -> Dict[str, Any]:
    """
    Build the evaluation environment used by row-wise expressions in mappings.

    Parameters
    ----------
    site_salt : str, optional
        Site-specific salt to expose to expressions. Available as:
          - SALT        (legacy alias some tests expect)
          - SITE_SALT   (explicit alias)
          - site_salt   (lowercase convenience)
    **overrides : Any
        Any symbols to override/add to the environment.

    Returns
    -------
    dict
        A dictionary suitable for use as the eval namespace.
    """
    env: Dict[str, Any] = {
        # salts (include legacy/test alias)
        "SALT": site_salt,
        "SITE_SALT": site_salt,
        "site_salt": site_salt,

        # helpers
        "parse_dt": parse_dt,
        "years_between": years_between,
        "boolify": boolify,
        "hash_id": hash_id,

        # normalizers
        "normalize_race": normalize_race,
        "normalize_eth": normalize_eth,
        "normalize_sex": normalize_sex,

        # safe builtins
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "len": len,
    }

    # Apply overrides last so callers can customize
    env.update(overrides)
    return env
