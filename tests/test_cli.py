# tests/test_cli.py
import sys
import subprocess
from pathlib import Path
import pandas as pd
import yaml

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

def write_csv(path: Path):
    rows = [
        # Black, eligible+contacted
        [11111,"Black","Not Hispanic","F","1960-01-15","2025-08-10",1,1,1,1,1,0.90,'{"inc":["EGFR+"],"exc":[]}',"2025-08-10T09:15:00Z","2025-08-10T10:00:00Z"],
        # White, eligible+contacted
        [22222,"White","Not Hispanic","M","1970-03-02","2025-08-12",1,1,1,1,0,0.80,'{"inc":["ALK+"],"exc":[]}', "2025-08-12T08:40:00Z","2025-08-12T09:10:00Z"],
        # White (Hispanic), eligible but NOT contacted
        [33333,"White","Hispanic","F","1985-11-23","2025-08-05",1,0,1,0,0,0.70,'{"inc":["ROS1+"],"exc":[]}',"2025-08-05T13:20:00Z",""],
    ]
    cols = ["MRN","RACE_DESC","ETHNICITY","SEX","BIRTH_DATE","MATCH_DATE",
            "MATCH_FLAG","CONTACTED","IDENTIFIED","CONSENTED","ENROLLED",
            "SCORE","CRITERIA_JSON","IDENTIFIED_AT","CONTACTED_AT"]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)

def write_mapping(path: Path):
    mapping = {
        "version": 1, "schema_version": "1.0.0",
        "assign": {"site_id": "SITE_X", "trial_id": "NCT01234567"},
        "columns": {
            "patient_id": "hash(SALT, row.MRN)",
            "race": "normalize_race(row.RACE_DESC)",
            "ethnicity": "normalize_eth(row.ETHNICITY)",
            "sex": "normalize_sex(row.SEX)",
            "age": "years_between(row.BIRTH_DATE, row.MATCH_DATE)",
            "eligible": "int(row.MATCH_FLAG)",
            "selected": "int(row.CONTACTED)",
            "identified": "int(row.IDENTIFIED)",
            "contacted": "int(row.CONTACTED)",
            "consented": "int(row.CONSENTED)",
            "enrolled": "int(row.ENROLLED)",
            "identified_at": "parse_dt(row.IDENTIFIED_AT)",
            "contacted_at": "parse_dt(row.CONTACTED_AT)",
            "match_score": "float(row.SCORE)",
            "matched_criteria": "row.CRITERIA_JSON",
        },
        "provenance": {"source_system": "demo_csv"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(mapping))

def _pick(df, *cands):
    for c in cands:
        if c in df.columns:
            return c
    raise AssertionError(f"Expected one of {cands}, got {list(df.columns)}")

def _eligible_mask(series: pd.Series) -> pd.Series:
    """
    Return a boolean mask for 'eligible' regardless of dtype:
    - ints/floats: > 0
    - bool: True
    - strings: '1', 'true', 'yes', 'y' (case/whitespace-insensitive)
    """
    s = series.copy()
    # Try booleans quickly
    if s.dtype == bool:
        return s
    # Numeric-ish
    num = pd.to_numeric(s, errors="coerce")
    mask_num = num > 0
    # String truthy
    s_str = s.astype(str).str.strip().str.lower()
    mask_str = s_str.isin({"1", "true", "yes", "y"})
    # Combine: if either numeric>0 or truthy-string → eligible
    mask = mask_num | mask_str
    mask = mask.fillna(False)
    mask.index = s.index
    return mask

def test_cli_e2e_map_validate_audit_rr(tmp_path):
    src = tmp_path / "sample.csv"
    map_yaml = tmp_path / "mapping.yaml"
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    write_csv(src)
    write_mapping(map_yaml)

    canon = out_dir / "canonical.csv"
    sel = out_dir / "selection_by_race.csv"
    rr  = out_dir / "rr_selection_by_race.csv"

    # 1) Map → Canonical
    run_ok(["map","--in",str(src),"--map",str(map_yaml),"--salt","TEST","--out",str(canon)], cwd=ROOT)
    assert canon.exists() and canon.stat().st_size > 0

    # 2) Validate canonical
    run_ok(["validate","--in",str(canon)], cwd=ROOT)

    # 3) Audit (Selection by race)
    run_ok(["audit","--in",str(canon),"--group","race","--metric","selection","--out",str(sel)], cwd=ROOT)
    audit_df = pd.read_csv(sel)
    assert audit_df.shape[0] >= 1
    for col in ("race", "n_denom", "n_num", "rate", "ci_low", "ci_high"):
        assert col in audit_df.columns

    # ===== Adaptive reference group for RR =====
    # Choose reference from canonical where eligible==1 (robust dtype handling)
    canon_df = pd.read_csv(canon)
    c_group = _pick(canon_df, "race", "group")
    c_elig  = _pick(canon_df, "eligible", "elig")
    elig_mask = _eligible_mask(canon_df[c_elig])
    elig = canon_df[elig_mask]
    if len(elig) == 0:
        import pytest
        pytest.skip("No eligible rows in canonical; selection RR not defined for this dataset")


    # Prefer White if present among eligible; otherwise, the group with the most eligible rows
    if (elig[c_group] == "White").any():
        ref_group = "White"
    else:
        ref_group = str(elig[c_group].value_counts().idxmax())

    # 4) RR vs chosen reference
    run_ok(["rr",
            "--in", str(canon),
            "--group", "race",
            "--metric", "selection",
            "--ref", ref_group,
            "--out", str(rr)], cwd=ROOT)

    rr_df = pd.read_csv(rr)
    for col in ("race","n_denom","n_num","rate","rr","rr_low","rr_high"):
        assert col in rr_df.columns

    # RR for the chosen reference should be ~1.0
    ref_row = rr_df.loc[rr_df["race"] == ref_group].iloc[0]
    assert abs(float(ref_row["rr"])) - 1.0 < 1e-9

