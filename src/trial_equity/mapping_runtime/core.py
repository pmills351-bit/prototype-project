from __future__ import annotations

from typing import Any, Dict, Mapping, Union

import pandas as pd

from .adapters import safe_builtins, default_env


Spec = Union[str, Mapping[str, Any]]


def _looks_like_expr(spec: str) -> bool:
    """
    Heuristic: decide if a plain string is an expression.
    We only eval when it obviously references code/row or is prefixed with '='.
    """
    s = spec.strip()
    if not s:
        return False
    if s.startswith("="):
        return True
    # obvious signs of an expression
    expr_tokens = (
        "row", "(", ")", "[", "]", "{", "}", " and ", " or ", " not ",
        "==", "!=", ">=", "<=", " years_between", " boolify", " hash_id"
    )
    return any(tok in s for tok in expr_tokens)


def _eval_row_expr(df: pd.DataFrame, expr: str, env: Dict[str, Any]) -> pd.Series:
    """
    Evaluate a Python expression per-row with a restricted environment.
    """
    code = expr.lstrip("=")  # allow "=..." for explicit exprs
    sb = safe_builtins()
    env_dict = default_env(env.get("SALT", ""))  # fresh per call

    def _apply_one(row: pd.Series):
        local_vars = {"row": row}
        try:
            return eval(code, {"__builtins__": {}}, {**env_dict, **env, **local_vars, **sb})
        except Exception as e:
            raise ValueError(f"Failed to eval row expr: {expr!r}: {e}") from e

    return df.apply(_apply_one, axis=1)


def _resolve_value(df_in: pd.DataFrame, spec: Spec, env: Dict[str, Any]) -> Any:
    """
    Resolve one output column spec. Supports:
      - literal string/number/bool
      - reference to an input column (string that matches a column name)
      - dict with key 'expr' holding a Python row expression
      - plain string that 'looks like' an expression
    """
    # dict form: {"expr": "..."}
    if isinstance(spec, Mapping):
        if "expr" in spec:
            return _eval_row_expr(df_in, str(spec["expr"]), env)
        # not an expr dict -> treat as literal string
        return str(spec)

    # primitive types
    if not isinstance(spec, str):
        return spec

    # reference to input column
    if spec in df_in.columns:
        return df_in[spec]

    # expression-ish string?
    if _looks_like_expr(spec):
        return _eval_row_expr(df_in, spec, env)

    # Otherwise treat as literal string (e.g., versions like "1.0.0")
    return spec


def _build_eval_env(site_salt: str) -> Dict[str, Any]:
    """
    Public helper exposed for tests: returns the expression environment
    (functions and constants), without any row bound.
    """
    sb = safe_builtins()
    env = default_env(site_salt)
    return {**env, **sb}


def apply_mapping(df_in: pd.DataFrame, mapping: Mapping[str, Spec], default_site_salt: str = "") -> pd.DataFrame:
    """
    Apply a mapping spec to an input DataFrame.

    `mapping` is a dict: output_column -> spec (literal/column/expr).
    """
    if not isinstance(df_in, pd.DataFrame):
        raise TypeError("df_in must be a pandas DataFrame")
    if not isinstance(mapping, Mapping):
        raise TypeError("mapping must be a mapping of output_column -> spec")

    env = {"SALT": str(default_site_salt)}
    out_cols: Dict[str, Any] = {}

    for out_col, spec in mapping.items():
        out_cols[str(out_col)] = _resolve_value(df_in, spec, env)

    df_out = pd.DataFrame(out_cols, index=df_in.index if len(out_cols) else None)
    return df_out
