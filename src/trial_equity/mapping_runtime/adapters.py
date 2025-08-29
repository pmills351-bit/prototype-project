from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from .helpers import parse_dt, years_between, boolify, hash_id


def safe_builtins() -> Dict[str, Any]:
    """
    A minimal, whitelisted set of Python builtins that are safe for eval context.
    """
    return {
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "len": len,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
    }


def default_env(site_salt: str) -> Dict[str, Any]:
    """
    Functions, variables, and helpers available to mapping expressions.
    """
    env: Dict[str, Any] = {
        # helpers
        "parse_dt": parse_dt,
        "years_between": years_between,
        "boolify": boolify,
        "hash_id": hash_id,
        # pandas convenience
        "pd": pd,
        # a symbolic salt available to expressions
        "SALT": site_salt,
    }
    return env
