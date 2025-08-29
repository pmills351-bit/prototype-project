"""
Export builder for DAP packet, HTI-1 transparency card, and Part 11 audit pack.
"""
from __future__ import annotations
import json, zipfile
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from .audit_trail import AuditTrail

UTC = timezone.utc

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

    def write_json(self, name: str, payload: Dict[str, Any]) -> Path:
        p = self.out / f"{name}.json"
        payload["_meta"] = {"export_version": self.ctx.version, "generated": datetime.now(UTC).isoformat()}
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.audit.record(actor="system", role="export", action="write", record_type=name, record_id=str(p.name), after_hash="", signature_id="")
        return p

    def build_dap_packet(self, payload: Dict[str, Any]) -> Path:
        payload["schema_version"] = "dap.v1"
        payload.setdefault("study_id", self.ctx.study_id)
        payload.setdefault("data_cut", self.ctx.data_cut)
        return self.write_json("DAP_Packet_v1", payload)

    def build_transparency_card(self, payload: Dict[str, Any]) -> Path:
        payload["schema_version"] = "hti1.card.v1"
        payload.setdefault("artifact_id", "EquiEnroll-TransparencyCard")
        payload.setdefault("version", self.ctx.version)
        return self.write_json("TransparencyCard_v1", payload)

    def build_audit_pack(self) -> Path:
        self.audit.write_hash_manifest()
        zpath = self.out / f"AuditPack_v1_{self.ctx.data_cut}.zip"
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in (self.out / "audit_pack").rglob("*"):
                if p.is_file():
                    z.write(p, arcname=f"audit_pack/{p.relative_to(self.out / 'audit_pack')}")
        return zpath
