# EquiEnroll Drop-in Files (Pilot Upgrade)

Copy these into your repo root, preserving paths.

## Files
- `src/trial_equity/stats.py` — Wilson CI utility
- `src/trial_equity/audit_trail.py` — append-only audit trail with hash-chaining + manifest
- `src/trial_equity/export_builder.py` — builds DAP/HTI-1 JSON and AuditPack ZIP
- `src/trial_equity/cli.py` — CLI to generate exports from CSV
- `src/trial_equity/__init__.py` — public exports
- `src/app_api.py` — FastAPI endpoint (optional)
- `app_streamlit_audit_pilot.py` — Streamlit app with **Compliance Exports (v1)**
- `schemas/*.json` — JSON Schemas (v1)
- `tests/test_*.py` — smoke tests for exports/audit trail
- `.env.example`, `Dockerfile`, `docker-compose.yml`

## Quick start
```bash
# 1) Copy files into your repo
# 2) Create and activate your env
pip install pandas fastapi pydantic uvicorn streamlit pytest

# 3) Generate exports via CLI
python -m trial_equity.cli export dap --study ABC-123 --data-cut 2025-08-29 --out out/ --from-csv data/mock_recruitment.csv
python -m trial_equity.cli export hti1 --out out/
python -m trial_equity.cli export audit-pack --out out/ --study ABC-123 --data-cut 2025-08-29

# 4) Or run the pilot Streamlit app
streamlit run app_streamlit_audit_pilot.py
```

## Notes
- DAP goals default to proportional share of selected in the CSV. Replace with study-specific goals when available.
- PDFs can be added later; JSON + ZIP cover the functional acceptance for v1.
