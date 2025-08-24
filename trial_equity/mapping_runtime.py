from __future__ import annotations
import yaml
import uuid
import datetime
import pandas as pd
from typing import Dict, Any

from .normalize import normalize_race, normalize_eth, normalize_sex
from .io_utils import parse_dt, years_between, hash_id

# Whitelisted functions available to YAML expressions
ALLOWED_FUNCS = {
    "normalize_race": normalize_race,
    "normalize_eth": normalize_eth,
    "normalize_sex": normalize_sex,
    "hash": hash_id,                 # usage: hash(SALT, row['MRN'])
    "parse_dt": parse_dt,
    "years_between": years_between,
    "bool": bool,
    "int": int,
    "float": float,
    "str": str,
}

def _safe_eval(expr: str, row: Dict[str, Any], vars: Dict[str, Any]) -> Any:
    """
    Evaluates a small expression from YAML in a restricted environment.
    NOTE: In your YAML, always access columns as row['COL_NAME'] (dict style).
    """
    env = {"__builtins__": {}}   # block builtins
    env.update(ALLOWED_FUNCS)
    env.update(vars)
    env["row"] = row
    return eval(expr, env, {})   # restricted env

def apply_mapping(
    df: pd.DataFrame,
    mapping: Dict[str, Any],
    default_site_salt: str = "SITE_SALT",
) -> pd.DataFrame:
    """
    Apply YAML mapping rules to an input DataFrame to produce Canonical v1 rows.
    The mapping dict supports:
      assign:   constant fields (e.g., site_id, trial_id)
      columns:  field -> expression (e.g., "race": "normalize_race(row['RACE_DESC'])")
      provenance.source_system
      schema_version
    """
    assign = mapping.get("assign", {}) or {}
    cols_map = mapping.get("columns", {}) or {}
    prov = mapping.get("provenance", {}) or {}
    schema_version = mapping.get("schema_version", "1.0.0")

    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    batch_id = str(uuid.uuid4())
    vars = {"SALT": default_site_salt, "load_time": now}

    out_rows = []
    for _, r in df.iterrows():
        row = r.to_dict()
        out = {}

        # 1) constants
        for k, v in assign.items():
            out[k] = v

        # 2) mapped columns via expression (or pass-through if expression fails)
        for k, expr in cols_map.items():
            try:
                if isinstance(expr, str):
                    out[k] = _safe_eval(expr, row, vars)
                else:
                    out[k] = None
            except Exception:
                # fallback to direct column value (if user provided a plain col name)
                out[k] = row.get(expr, None)

        # 3) provenance
        out["source_system"] = prov.get("source_system", "unknown")
        out["schema_version"] = schema_version
        out["ingested_at"] = now.isoformat()
        out["load_batch_id"] = batch_id

        out_rows.append(out)

    return pd.DataFrame(out_rows)

def load_mapping(path: str) -> Dict[str, Any]:
    """Load a YAML mapping file from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
