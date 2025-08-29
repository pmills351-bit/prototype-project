from pathlib import Path
import math
import pandas as pd
import yaml

from trial_equity.mapping_runtime import apply_mapping
from trial_equity.schema import validate_canonical_v1
from trial_equity.enums import normalize_race, normalize_eth, normalize_sex
from trial_equity.metrics import group_rate_ci, risk_ratios

ROOT = Path(__file__).resolve().parents[1]  # repo root
CASE = ROOT / "data" / "cases" / "case-basic"

def _coerce_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure boolean-ish flags are 0/1 floats for metrics."""
    for col in ("eligible", "selected", "contacted", "consented", "enrolled"):
        if col in df.columns:
            df[col] = df[col].astype(float).fillna(0.0)
    return df

def test_case_basic_mapping_to_canonical_and_metrics():
    # 1) Load inputs
    src = CASE / "sample.csv"
    map_yaml = CASE / "mapping.yaml"
    assert src.exists(), f"Missing sample input: {src}"
    assert map_yaml.exists(), f"Missing mapping: {map_yaml}"

    df_in = pd.read_csv(src)
    mapping = yaml.safe_load(map_yaml.read_text())

    # 2) Apply mapping with a fixed salt to make patient_id deterministic
    df_out = apply_mapping(df_in, mapping, default_site_salt="TEST")

    # 3) Normalize enums (defensive)
    df_out["race"] = df_out["race"].apply(normalize_race)
    df_out["ethnicity"] = df_out["ethnicity"].apply(normalize_eth)
    df_out["sex"] = df_out["sex"].apply(normalize_sex)

    # 4) Coerce flags
    df_out = _coerce_flags(df_out)

    # 5) Validate canonical
    validate_canonical_v1(df_out)

    # Basic shape & uniqueness checks
    req = ["site_id","trial_id","patient_id","age","race","sex","eligible","selected"]
    for c in req:
        assert c in df_out.columns, f"missing required column: {c}"
    assert df_out["patient_id"].nunique() == len(df_out), "patient_id must be unique per row"

    # 6) Selection parity: contacted | eligible
    sel = group_rate_ci(df_out, group="race", numerator="contacted", denominator="eligible")
    assert {"race","n_denom","n_num","rate","ci_low","ci_high"} <= set(sel.columns)

    # 7) RR vs White on selection
    rr = risk_ratios(sel, group="race", ref="White")
    assert {"race","n_denom","n_num","rate","ci_low","ci_high","rr","rr_low","rr_high"} <= set(rr.columns)

def test_patient_hash_changes_with_salt():
    src = CASE / "sample.csv"
    map_yaml = CASE / "mapping.yaml"
    df_in = pd.read_csv(src)
    mapping = yaml.safe_load(map_yaml.read_text())

    a = apply_mapping(df_in, mapping, default_site_salt="SALT_A")["patient_id"]
    b = apply_mapping(df_in, mapping, default_site_salt="SALT_B")["patient_id"]

    # Same number of rows, but different hashed IDs with different salts
    assert len(a) == len(b)
    assert not a.equals(b), "patient_id should change when SITE_SALT changes"

def test_cli_parity_case_basic(tmp_path):
    """End-to-end via CLI to mirror how case bundles are used."""
    import subprocess, sys

    canon = tmp_path / "canonical.csv"
    sel_out = tmp_path / "selection_by_race.csv"
    rr_out  = tmp_path / "rr_selection_by_race.csv"

    def run_ok(args):
        cmd = [sys.executable, "-m", "trial_equity.cli"] + args
        r = subprocess.run(cmd, text=True, cwd=ROOT, capture_output=True)
        assert r.returncode == 0, f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
        return r

    # map -> validate -> audit -> rr
    run_ok(["map","--in",str(CASE/"sample.csv"),"--map",str(CASE/"mapping.yaml"),
            "--salt","TEST","--out",str(canon)])
    run_ok(["validate","--in",str(canon)])
    run_ok(["audit","--in",str(canon),"--group","race","--metric","selection","--out",str(sel_out)])
    run_ok(["rr","--in",str(canon),"--group","race","--metric","selection","--ref","White","--out",str(rr_out)])

    sel_df = pd.read_csv(sel_out)
    rr_df  = pd.read_csv(rr_out)
    assert len(sel_df) >= 1
    assert {"race","n_denom","n_num","rate","ci_low","ci_high"} <= set(sel_df.columns)
    assert {"race","n_denom","n_num","rate","ci_low","ci_high","rr","rr_low","rr_high"} <= set(rr_df.columns)
