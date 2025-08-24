import sys
import subprocess
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def run_ok(args, cwd=None):
    """
    Run the CLI via the module runner to avoid Windows shim/path issues.
    Example: python -m trial_equity.cli map --in ... --out ...
    """
    cmd = [sys.executable, "-m", "trial_equity.cli"] + args
    r = subprocess.run(cmd, text=True, cwd=cwd, capture_output=True)
    assert r.returncode == 0, (
        f"FAILED: {' '.join(cmd)}\n"
        f"STDOUT:\n{r.stdout}\n"
        f"STDERR:\n{r.stderr}"
    )
    return r

def test_cli_map_validate_audit_and_rr(tmp_path):
    # Inputs (use repo fixtures)
    rich = ROOT / "data" / "input" / "sample_input_rich.csv"
    mapping = ROOT / "data" / "mappings" / "mapping_demo.yaml"
    assert rich.exists(), f"Missing sample input: {rich}"
    assert mapping.exists(), f"Missing mapping file: {mapping}"

    # Outputs
    canon = tmp_path / "canonical.csv"
    audit_out = tmp_path / "selection_by_race.csv"
    rr_out = tmp_path / "rr_selection_by_race.csv"

    # 1) Map → Canonical
    run_ok(["map",
            "--in", str(rich),
            "--map", str(mapping),
            "--salt", "TEST",
            "--out", str(canon)],
           cwd=ROOT)
    assert canon.exists() and canon.stat().st_size > 0

    # 2) Validate canonical
    run_ok(["validate", "--in", str(canon)], cwd=ROOT)

    # 3) Audit (Selection by race)
    run_ok(["audit",
            "--in", str(canon),
            "--group", "race",
            "--metric", "selection",
            "--out", str(audit_out)],
           cwd=ROOT)
    audit_df = pd.read_csv(audit_out)
    assert audit_df.shape[0] >= 1
    # basic schema sanity
    for col in ("race", "n_denom", "n_num", "rate", "ci_low", "ci_high"):
        assert col in audit_df.columns, f"Missing '{col}' in audit table"

    # 4) RR vs White (Selection by race)
    run_ok(["rr",
            "--in", str(canon),
            "--group", "race",
            "--metric", "selection",
            "--ref", "White",
            "--out", str(rr_out)],
           cwd=ROOT)
    rr_df = pd.read_csv(rr_out)
    for col in ("race", "n_denom", "n_num", "rate", "rr", "rr_low", "rr_high"):
        assert col in rr_df.columns, f"Missing '{col}' in RR table"

    # If White exists in the table, RR for White should be ~1.0
    if (rr_df["race"] == "White").any():
        ref_row = rr_df.loc[rr_df["race"] == "White"].iloc[0]
        assert abs(float(ref_row["rr"]) - 1.0) < 1e-9
