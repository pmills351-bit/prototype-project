"""
Append-only audit trail with hash chaining and signature linkage.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import csv, hashlib, json

UTC = timezone.utc

@dataclass
class TrailEvent:
    timestamp: str
    actor: str
    role: str
    action: str
    record_type: str
    record_id: str
    before_hash: str
    after_hash: str
    signature_id: str
    prev_hash: str
    this_hash: str

class AuditTrail:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.trails_dir = self.root / "trails"
        self.trails_dir.mkdir(parents=True, exist_ok=True)
        self.trail_csv = self.trails_dir / "AuditTrail.csv"
        self.hash_manifest = self.trails_dir / "HashManifest.sha256"

        if not self.trail_csv.exists():
            with self.trail_csv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["timestamp","actor","role","action","record_type","record_id","before_hash","after_hash","signature_id","prev_hash","this_hash"])

    @staticmethod
    def _hash_bytes(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def record(self, *, actor: str, role: str, action: str,
               record_type: str, record_id: str,
               before_hash: str = "", after_hash: str = "",
               signature_id: str = "") -> TrailEvent:
        ts = datetime.now(UTC).isoformat()
        prev = ""
        if self.trail_csv.exists():
            with self.trail_csv.open("r", encoding="utf-8") as f:
                lines = f.read().strip().splitlines()
                if len(lines) > 1:
                    prev = lines[-1].split(",")[-1]
        payload = json.dumps({
            "ts": ts, "actor": actor, "role": role, "action": action,
            "record_type": record_type, "record_id": record_id,
            "before_hash": before_hash, "after_hash": after_hash,
            "signature_id": signature_id, "prev_hash": prev
        }, sort_keys=True).encode("utf-8")
        this_hash = self._hash_bytes(payload)

        ev = TrailEvent(ts, actor, role, action, record_type, record_id, before_hash, after_hash, signature_id, prev, this_hash)
        with self.trail_csv.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                ev.timestamp, ev.actor, ev.role, ev.action, ev.record_type, ev.record_id,
                ev.before_hash, ev.after_hash, ev.signature_id, ev.prev_hash, ev.this_hash
            ])
        return ev

    def write_hash_manifest(self) -> None:
        pack_root = self.root
        entries = []
        for p in pack_root.rglob("*"):
            if p.is_file():
                entries.append(f"{self._hash_file(p)}  {p.relative_to(pack_root)}")
        entries.sort()
        self.hash_manifest.write_text("\n".join(entries), encoding="utf-8")
