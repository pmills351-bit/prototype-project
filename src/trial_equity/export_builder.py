"""
Export builder for DAP packet, HTI-1 transparency card, and Part 11 audit pack.
Adds:
- Deterministic mode via EQUIENROLL_DETERMINISTIC=1
- Optional JSON Schema validation via EQUIENROLL_VALIDATE=1
- Signature manifest writer (pilot-friendly) for Part 11 linkage
"""
from __future__ import annotations
import os, json, zipfile
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from .audit_trail import AuditTrail

UTC = timezone.utc

def _safe_import_jsonschema():
    try:
        import jsonschema as j
        return j
    except Exception:
        return None

def _find_schemas_dir() -> Optional[Path]:
    # Search common locations starting from CWD and module path
    candidates = []
    try:
        here = Path(__file__).resolve()
        candidates += [here.parent, *list(here.parents)]
    except Exception:
        pass
    candidates += [Path.cwd()]
    seen = set()
    for base in candidates:
        if base is None: continue
        try:
            p = Path(base) / "schemas"
            if p.exists() and p.is_dir():
                key = str(p.resolve())
                if key in seen: 
                    continue
                seen.add(key)
                return p
        except Exception:
            continue
    return None

@dataclass
class ExportContext:
    study_id: str
    data_cut: str
    out_dir: str  # where to place PDFs/JSON and packs
    version: str = "1.0.0"

class ExportBuilder:
    def __init__(self, ctx: ExportContext):
        self.ctx = ctx
        self.out = Path(ctx.out_dir); self.out.mkdir(parents=True, exist_ok=True)
        self.audit = AuditTrail(self.out / "audit_pack" )
        self.schemas_dir = _find_schemas_dir()
        self.js = _safe_import_jsonschema()

    # ---------------- helpers ----------------
    def _deterministic_ts(self) -> str:
        deterministic = os.getenv("EQUIENROLL_DETERMINISTIC", "0") == "1"
        return f"{self.ctx.data_cut}T00:00:00Z" if deterministic else datetime.now(UTC).isoformat()

    def _validate(self, schema_name: str, payload: Dict[str, Any]) -> None:
        if os.getenv("EQUIENROLL_VALIDATE", "0") != "1":
            return
        if not self.js or not self.schemas_dir:
            return
        schema_path = self.schemas_dir / schema_name
        if not schema_path.exists():
            return
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.js.Draft202012Validator(schema).validate(payload)

    def write_json(self, name: str, payload: Dict[str, Any]) -> Path:
        p = self.out / f"{name}.json"
        payload = dict(payload)  # shallow copy
        payload.setdefault("_meta", {})
        payload["_meta"].update({"export_version": self.ctx.version, "generated": self._deterministic_ts()})
        # Validate (optional) prior to write
        if name.startswith("DAP_Packet"):
            self._validate("dap.v1.schema.json", payload)
        elif name.startswith("TransparencyCard"):
            self._validate("hti1.card.v1.schema.json", payload)

        p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.audit.record(actor="system", role="export", action="write", record_type=name, record_id=str(p.name), after_hash="", signature_id="")
        return p

    # ---------------- public builders ----------------
    def build_dap_packet(self, payload: Dict[str, Any]) -> Path:
        payload = dict(payload)
        payload["schema_version"] = "dap.v1"
        payload.setdefault("study_id", self.ctx.study_id)
        payload.setdefault("data_cut", self.ctx.data_cut)
        return self.write_json("DAP_Packet_v1", payload)

    def build_transparency_card(self, payload: Dict[str, Any]) -> Path:
        payload = dict(payload)
        payload["schema_version"] = "hti1.card.v1"
        payload.setdefault("artifact_id", "EquiEnroll-TransparencyCard")
        payload.setdefault("version", self.ctx.version)
        return self.write_json("TransparencyCard_v1", payload)

    def build_signature_manifest(self, signers: List[Dict[str, Any]]) -> Path:
        """Write a pilot-friendly SignatureManifest.json linking signers to current export files.

        signers: list of {"role":..., "name":..., "purpose": "approve/review", "time": ISO8601 or None}

        """
        sig_dir = self.out / "audit_pack" / "signatures"
        sig_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for fname in ("DAP_Packet_v1.json", "TransparencyCard_v1.json"):
            f = self.out / fname
            if f.exists():
                files.append({"file": fname, "sha256": self.audit._hash_file(f)})
        # normalize signers (fill time if missing)
        now = self._deterministic_ts()
        norm = []
        for s in (signers or []):
            d = {"role": s.get("role",""), "name": s.get("name",""), "purpose": s.get("purpose","approve"), "time": s.get("time") or now}
            norm.append(d)
        payload = {"schema_version": "sig.v1", "files": files, "signers": norm}
        path = sig_dir / "SignatureManifest.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.audit.record(actor="system", role="export", action="write", record_type="SignatureManifest", record_id=str(path.name), after_hash="", signature_id="pilot-v1")
        return path

    def build_audit_pack(self) -> Path:
        self.audit.write_hash_manifest()
        zpath = self.out / f"AuditPack_v1_{self.ctx.data_cut}.zip"
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in (self.out / "audit_pack").rglob("*"):
                if p.is_file():
                    z.write(p, arcname=f"audit_pack/{p.relative_to(self.out / 'audit_pack')}" )
        return zpath
