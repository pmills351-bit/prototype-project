import math
from pathlib import Path
import pandas as pd
import yaml

from trial_equity.mapping_runtime import apply_mapping
from trial_equity.schema import validate_canonical_v1
from trial_equity.metrics import group_rate_ci, risk_ratios

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "data" / "cases" / "case-diverse"

def test_case_diverse_mapping_to_canonical_and_metrics():
    # 1) Load inputs
    src = CASE / "sample.csv"
    map_yaml = CASE / "mapping.yaml"
    assert src.exists(), f"Missing sample input: {src}"
    assert map_yaml.exists(), f"Missing mapping: {map_yaml}"

    df_in = pd.read_csv(src)
    mapping = yaml.safe_load(map_yaml.read_text())

    # 2) Apply mapping with a fixed salt to make patient_id deterministic
    df_out = apply_mapping(df_in, mapping, default_site_salt="TEST_SALT")

    # 3) Validate canonical schema
    validate_canonical_v1(df_out)

    # 4) Basic sanity: required columns present and types look right
    for col in ["site_id","trial_id","patient_id","age","race","sex","ethnicity",
                "eligible","selected","contacted","consented","enrolled"]:
        assert col in df_out.columns, f"Missing {col}"
    assert df_out["patient_id"].nunique() == len(df_out), "patient_id should be unique"
    assert set(df_out["race"].dropna().unique()) <= {
        "White","Black or African American","Asian","Unknown"
    }

    # 5) Selection parity: Contacted | Eligible
    sel = group_rate_ci(df_out, group_col="race", num_col="contacted", den_cond_col="eligible")
    for c in ("race","n_denom","n_num","rate","ci_low","ci_high"):
        assert c in sel.columns, f"Missing {c} in selection table"

    # Ensure at least 3 groups reported
    assert sel.shape[0] >= 3

    # 6) Risk ratios vs White (Selection)
    rr = risk_ratios(sel, group_col="race", ref="White")
    for c in ("race","n_denom","n_num","rate","rr","rr_low","rr_high"):
        assert c in rr.columns, f"Missing {c} in RR table"

def test_patient_hash_changes_with_salt():
    df_in = pd.read_csv(CASE / "sample.csv")
    mapping = yaml.safe_load((CASE / "mapping.yaml").read_text())

    a = apply_mapping(df_in, mapping, default_site_salt="SALT_A")["patient_id"]
    b = apply_mapping(df_in, mapping, default_site_salt="SALT_B")["patient_id"]

    # With only salt changed, the generated ids must differ
    assert not a.equals(b), "patient_id must change when site salt changes"

def test_cli_parity_case_diverse(tmp_path):
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
    run_ok([
        "map","--in",str(CASE/"sample.csv"),"--map",str(CASE/"mapping.yaml"),
        "--salt","TEST","--out",str(canon)
    ])
    run_ok(["validate","--in",str(canon)])
    run_ok([
        "audit","--in",str(canon),"--group","race","--metric","selection",
        "--out",str(sel_out)
    ])
    run_ok([
        "rr","--in",str(canon),"--group","race","--metric","selection",
        "--ref","White","--out",str(rr_out)
    ])

    # quick shape sanity
    sel_df = pd.read_csv(sel_out)
    rr_df  = pd.read_csv(rr_out)
    assert sel_df.shape[0] >= 3
    assert rr_df.shape[0] >= 3
