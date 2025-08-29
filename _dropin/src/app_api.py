"""
Minimal FastAPI service exposing export endpoints.
Run: uvicorn app_api:app --reload --port 8000
"""
from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import date
from pathlib import Path
from trial_equity.export_builder import ExportBuilder, ExportContext

app = FastAPI(title="EquiEnroll API", version="1.0.0")

class DapPayload(BaseModel):
    study_id: str
    data_cut: date
    csv_path: str

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/export/dap")
def export_dap(payload: DapPayload):
    ctx = ExportContext(study_id=payload.study_id, data_cut=str(payload.data_cut), out_dir="out")
    eb = ExportBuilder(ctx)
    from trial_equity.cli import build_dap_from_csv
    dap = build_dap_from_csv(Path(payload.csv_path))
    path = eb.build_dap_packet(dap)
    return {"ok": True, "path": str(path)}
