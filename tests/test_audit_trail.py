from pathlib import Path
from trial_equity.audit_trail import AuditTrail

def test_hash_chain(tmp_path: Path):
    a = AuditTrail(tmp_path / "pack")
    e1 = a.record(actor="u", role="r", action="create", record_type="x", record_id="1")
    e2 = a.record(actor="u", role="r", action="update", record_type="x", record_id="1", before_hash=e1.this_hash)
    assert e2.prev_hash == e1.this_hash
    a.write_hash_manifest()
    assert (tmp_path / "pack" / "trails" / "HashManifest.sha256").exists()
