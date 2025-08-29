import os, sys, json, hashlib, zipfile, subprocess
from pathlib import Path
import pytest

# Make src/ importable when running pytest from repo root
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

jsonschema = pytest.importorskip("jsonschema")

from trial_equity.export_builder import ExportBuilder, ExportContext
from trial_equity import cli as cli_mod  # uses build_dap_from_csv()

REQUIRED = ["race","ethnicity","sex","age","eligible","contacted","selected"]

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # Deterministic + validate by default
    monkeypatch.setenv("EQUIENROLL_DETERMINISTIC", "1")
    monkeypatch.setenv("EQUIENROLL_VALIDATE", "1")
    yield

@pytest.fixture
def out_dir(tmp_path) -> Path:
    p = tmp_path / "out"
    p.mkdir(parents=True, exist_ok=True)
    return p

@pytest.fixture
def sample_csv(tmp_path) -> Path:
    # Messy headers to exercise --loose mapping
    csv = tmp_path / "sample.csv"
    csv.write_text(
        "Race,hispanic,gender,age_years,pre_screen_eligible,screened,enrolled\n"
        "White,non-hispanic,m,55,1,1,1\n"
        "Black or African American,hispanic,f,42,1,1,0\n"
        "Asian,non-hispanic,f,29,1,0,0\n",
        encoding="utf-8",
    )
    return csv

@pytest.fixture
def schemas():
    dap_s = json.loads((ROOT / "schemas" / "dap.v1.schema.json").read_text(encoding="utf-8"))
    hti_s = json.loads((ROOT / "schemas" / "hti1.card.v1.schema.json").read_text(encoding="utf-8"))
    return dap_s, hti_s

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def test_cli_help_shows_loose_and_map():
    res = subprocess.run([sys.executable, "-m", "trial_equity.cli", "export", "dap", "-h"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    out = res.stdout.lower()
    assert "--loose" in out and "--map" in out

def test_dap_loose_mapping_and_schema(out_dir, sample_csv, schemas):
    dap_schema, _ = schemas
    ctx = ExportContext(study_id="ABC-123", data_cut="2025-08-28", out_dir=str(out_dir))
    eb = ExportBuilder(ctx)

    payload = cli_mod.build_dap_from_csv(sample_csv, mapping=None, loose=True)
    path = eb.build_dap_packet(payload)
    assert path.exists(), "DAP packet was not written"

    # Validate vs schema (also validated during write_json)
    data = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(dap_schema).validate(data)
    assert data["schema_version"] == "dap.v1"
    assert len(data["subgroups"]) > 0

def test_hti1_generation_and_schema(out_dir, schemas):
    _, hti_schema = schemas
    ctx = ExportContext(study_id="ABC-123", data_cut="2025-08-28", out_dir=str(out_dir))
    eb = ExportBuilder(ctx)
    card = {
        "artifact_id": "EquiEnroll-TransparencyCard",
        "intended_use": "Recruitment fairness analytics for clinical trials",
        "inputs": REQUIRED,
        "logic_summary": "Parity gaps + Wilson CIs; action queues for under-reached groups",
        "performance": [],
        "limitations": ["Small-n instability in rare subgroups"],
        "irm": {"risks":["missing race"], "mitigations":["guardrails"], "monitoring":"quarterly fairness check"},
        "version": ctx.version,
    }
    path = eb.build_transparency_card(card)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(hti_schema).validate(data)
    assert data["schema_version"] == "hti1.card.v1"

def test_determinism_across_runs(out_dir, sample_csv):
    ctx = ExportContext(study_id="ABC-123", data_cut="2025-08-28", out_dir=str(out_dir))
    eb = ExportBuilder(ctx)
    payload = cli_mod.build_dap_from_csv(sample_csv, mapping=None, loose=True)
    p1 = eb.build_dap_packet(payload)
    h1 = _sha256(p1)

    payload2 = cli_mod.build_dap_from_csv(sample_csv, mapping=None, loose=True)
    p2 = eb.build_dap_packet(payload2)
    h2 = _sha256(p2)
    assert h1 == h2, "Deterministic mode did not produce identical bytes"

def test_signatures_cli_and_audit_pack(out_dir, sample_csv):
    # Prepare DAP + HTI-1 (so hashing has files)
    ctx = ExportContext(study_id="ABC-123", data_cut="2025-08-28", out_dir=str(out_dir))
    eb = ExportBuilder(ctx)
    payload = cli_mod.build_dap_from_csv(sample_csv, mapping=None, loose=True)
    eb.build_dap_packet(payload)
    eb.build_transparency_card({
        "artifact_id":"EquiEnroll-TransparencyCard",
        "intended_use":"Recruitment fairness analytics for clinical trials",
        "inputs": REQUIRED, "logic_summary":"Parity gaps",
        "performance":[], "limitations":[], "irm":{}, "version": ctx.version
    })

    # Signers JSON
    signers_json = out_dir.parent / "example_signers.json"
    signers_json.write_text(json.dumps({
        "signers": [
            {"role":"Sponsor Rep","name":"Jane Smith","purpose":"approve","time":None},
            {"role":"Site Lead CRC","name":"Alex Doe","purpose":"review","time":None},
            {"role":"EquiEnroll","name":"System","purpose":"generate","time":None},
        ]
    }, indent=2), encoding="utf-8")

    # Call the real CLI subcommand
    cmd = [
        sys.executable, "-m", "trial_equity.cli", "export", "signatures",
        "--out", str(out_dir), "--study", "ABC-123", "--data-cut", "2025-08-28",
        "--from-json", str(signers_json),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"signatures CLI failed: {res.stderr}"
    sig_path = out_dir / "audit_pack" / "signatures" / "SignatureManifest.json"
    assert sig_path.exists(), "SignatureManifest.json not created"

    manifest = json.loads(sig_path.read_text(encoding="utf-8"))
    files = {f["file"]: f["sha256"] for f in manifest.get("files", [])}
    assert "DAP_Packet_v1.json" in files and len(files["DAP_Packet_v1.json"]) == 64
    assert "TransparencyCard_v1.json" in files and len(files["TransparencyCard_v1.json"]) == 64

    # Close audit pack & verify
    zpath = eb.build_audit_pack()
    assert zpath.exists()
    with zipfile.ZipFile(zpath, "r") as z:
        names = set(z.namelist())
    assert "audit_pack/trails/AuditTrail.csv" in names
    assert "audit_pack/trails/HashManifest.sha256" in names
    assert "audit_pack/signatures/SignatureManifest.json" in names

def test_schema_validation_catches_bad_payload(out_dir):
    os.environ["EQUIENROLL_VALIDATE"] = "1"
    ctx = ExportContext(study_id="ABC-123", data_cut="2025-08-28", out_dir=str(out_dir))
    eb = ExportBuilder(ctx)
    # Missing required fields -> should raise jsonschema error
    with pytest.raises(Exception):
        eb.write_json("DAP_Packet_v1", {"schema_version": "dap.v1"})