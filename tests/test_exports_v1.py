import json
from pathlib import Path
from trial_equity.export_builder import ExportBuilder, ExportContext
from trial_equity.cli import build_dap_from_csv

def test_build_dap_packet(tmp_path: Path):
    # Minimal CSV
    csv = tmp_path / "demo.csv"
    csv.write_text("race,ethnicity,sex,age,eligible,contacted,selected\nBlack,Non-Hispanic,F,67,1,1,1\n", encoding="utf-8")
    ctx = ExportContext(study_id="ABC-123", data_cut="2025-08-25", out_dir=str(tmp_path))
    eb = ExportBuilder(ctx)
    payload = build_dap_from_csv(csv)
    p = eb.build_dap_packet(payload)
    data = json.loads(p.read_text())
    assert data["schema_version"] == "dap.v1"
    assert data["study_id"] == "ABC-123"
    assert (tmp_path / "audit_pack" / "trails" / "AuditTrail.csv").exists()

def test_build_audit_pack(tmp_path: Path):
    ctx = ExportContext(study_id="ABC-123", data_cut="2025-08-25", out_dir=str(tmp_path))
    eb = ExportBuilder(ctx)
    eb.build_dap_packet({"subgroups": [], "milestones": [], "signatures": []})
    z = eb.build_audit_pack()
    assert z.exists()
