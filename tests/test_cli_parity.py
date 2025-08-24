import subprocess, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run_ok(cmd):
    r = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    assert r.returncode == 0, f"FAILED: {' '.join(cmd)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    return r

def test_cli_map_validate_audit_and_rr(tmp_path):
    # Prepare canonical via CLI on the rich input
    rich = ROOT / "data" / "input" / "sample_input_rich.csv"
    mapping = ROOT / "data" / "mappings" / "mapping_demo.yaml"
    canon = tmp_path / "canonical.csv"

    run_ok(["te","map","--in",str(rich),"--map",str(mapping),"--salt","TEST","--out",str(canon)])
    run_ok(["te","validate","--in",str(canon)])

    sel = tmp_path / "selection_by_race.csv"
    rr  = tmp_path / "rr_selection_by_race.csv"

    run_ok(["te","audit","--in",str(canon),"--group","race","--metric","selection","--out",str(sel)])
    run_ok(["te","rr","--in",str(canon),"--group","race","--metric","selection","--ref","White","--out",str(rr)])

    # check selection rates
    rates = {}
    with sel.open(newline="") as f:
        for row in csv.DictReader(f):
            rates[row["race"]] = float(row["rate"]) if row["rate"] else float("nan")
    assert round(rates["Asian"], 3) == 1.000
    assert round(rates["Black or African American"], 3) == 1.000
    assert round(rates["White"], 3) == 0.500

    # check RR
    rrs = {}
    with rr.open(newline="") as f:
        for row in csv.DictReader(f):
            rrs[row["race"]] = float(row["rr"]) if row["rr"] else float("nan")
    assert round(rrs["White"], 3) == 1.000
    assert rrs["Asian"] > 1.0
    assert rrs["Black or African American"] > 1.0
