# app_streamlit_audit.py
# ---------------------------------------------------------------------
# Bias & Equity Audit for Trial Recruitment — with Demo Artifacts
# Prepared in the role of a Patent Attorney (20+ yrs in software patents,
# healthcare/MedTech, AI/data science) — focus on portable demo artifacts
# for filings, grants, investor/pilot presentations (synthetic only).
# ---------------------------------------------------------------------

import os
import io
import json
import hashlib
import zipfile
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

# If your project provides this, we use it. Otherwise we degrade gracefully.
try:
    from src.fairness import summarize_fairness  # your existing module
    HAS_SUMMARIZE = True
except Exception:
    HAS_SUMMARIZE = False


# --------------------------- UI CONFIG --------------------------------
st.set_page_config(page_title="Bias & Equity Audit", layout="wide")
st.title("Bias & Equity Audit for Trial Recruitment")

st.markdown(
    "Upload a CSV with columns like: "
    "**race, ethnicity, sex, age, eligible (0/1), contacted (0/1), selected (0/1)**. "
    "Or use the bundled mock data."
)

# ------------------------ HELPERS (COMMON) -----------------------------
MOCK_PATH = "data/mock_recruitment.csv"

def load_dataset(file, use_mock: bool) -> pd.DataFrame:
    if use_mock:
        try:
            return pd.read_csv(MOCK_PATH)
        except FileNotFoundError:
            st.error("mock_recruitment.csv not found. Generate or place it at data/mock_recruitment.csv.")
            st.stop()
    else:
        if file is None:
            st.info('Upload a CSV or check "Use mock data" to proceed.')
            st.stop()
        return pd.read_csv(file)


# -------------------- DEMO ARTIFACTS (SYNTHETIC) ----------------------
# These demonstrate concrete examples for patent exhibits / demos.
# Marked synthetic, illustrative, non-limiting. No PHI.

def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def make_input_csv_bytes():
    df = pd.DataFrame([
        {"patient_id":"P001","race":"Black","ethnicity":"Non-Hispanic","sex":"F","age_band":"50-59","eligible":1,"contacted":1,"selected":0},
        {"patient_id":"P002","race":"White","ethnicity":"Non-Hispanic","sex":"M","age_band":"60-69","eligible":1,"contacted":0,"selected":0},
        {"patient_id":"P003","race":"Asian","ethnicity":"Non-Hispanic","sex":"F","age_band":"40-49","eligible":1,"contacted":1,"selected":1},
        {"patient_id":"P004","race":"Black","ethnicity":"Non-Hispanic","sex":"M","age_band":"50-59","eligible":1,"contacted":1,"selected":0},
        {"patient_id":"P005","race":"Hispanic","ethnicity":"Any","sex":"F","age_band":"30-39","eligible":1,"contacted":0,"selected":0},
    ])
    return df.to_csv(index=False).encode("utf-8")

def make_thresholds_json_bytes():
    cfg = {
        "reference_subgroup": {"race":"White","ethnicity":"Non-Hispanic"},
        "min_n": 20,
        "contact_rate_warn": 0.70,
        "disparity_ratio_fail": 0.80,
        "ci_method": "wilson",
        "bootstrap_reps": 2000
    }
    return (json.dumps(cfg, indent=2) + "\n").encode("utf-8")

def make_artifact_json_bytes(study_id="RS-2025-001", window="2025-Q2"):
    data = {
        "study_id": study_id,
        "window": window,
        "subgroup": {"race": "Black", "ethnicity": "Non-Hispanic"},
        "metrics": {
            "eligible": 42, "contacted": 28, "selected": 9,
            "contact_rate": 0.667, "contact_ci_wilson": [0.52, 0.79],
            "selection_rate": 0.214, "disparity_vs_ref": 0.78,
            "brier": 0.182
        },
        "compliance": {"status": "Borderline", "reasons": ["disparity_ratio<0.8"]},
        "generated_at": _utc_now(),
        "version": {"thresholds":"v1.2","metrics":"v0.9.3"}
    }
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")

def make_fhir_docref_bytes(study_id="RS-2025-001", window="2025-Q2",
                           artifact_filename="equity_audit_RS-2025-001_2025Q2.json"):
    docref = {
        "resourceType": "DocumentReference",
        "status": "current",
        "type": {"text": "Trial Recruitment Equity Audit"},
        "subject": {"reference": f"ResearchStudy/{study_id}"},
        "date": _utc_now(),
        "content": [{
            "attachment": {
                "contentType": "application/json",
                "title": artifact_filename,
                "url": "Binary/placeholder-id"  # replace in real integration
            }
        }]
    }
    return (json.dumps(docref, indent=2) + "\n").encode("utf-8")

def make_audit_log_line(prev_hash: str, artifact_bytes: bytes):
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    entry = {
        "event": "audit_artifact_created",
        "artifact_sha256": artifact_sha,
        "inputs": {"study_id":"RS-2025-001","window":"2025-Q2"},
        "sw_versions": {"engine":"1.0.4","ci":"wilson"},
        "user":"svc-equity-bot",
        "timestamp": _utc_now(),
        "prev_hash": prev_hash
    }
    # convenience: next entry should use this as prev_hash
    compact = json.dumps(entry, separators=(",", ":"), sort_keys=True).encode("utf-8")
    entry["next_prev_hash"] = hashlib.sha256(compact).hexdigest()
    return (json.dumps(entry) + "\n").encode("utf-8")

def transparency_summary_text():
    return (
        "INTENDED USE: Audit equity in clinical trial recruitment by subgroup.\n"
        "LOGIC SUMMARY: Partition by demographics; compute rates, Wilson CI, bootstrap uncertainty, "
        "disparity vs reference; compare to thresholds; flag/alert; gate workflows if non-compliant.\n"
        "LIMITATIONS: Small-n volatility; data quality sensitivity.\n"
        "RISK MGMT: Min-n guards; control-limit alerts; manual review queue; immutable audit logging; RBAC.\n"
        "EVALUATION: Periodic calibration (Brier + reliability); quarterly fairness review.\n"
    )

def make_zip_bytes(files: dict) -> bytes:
    """
    files: dict[name -> bytes]
    """
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, fbytes in files.items():
            zf.writestr(fname, fbytes)
    mem.seek(0)
    return mem.read()


# -------------------------- SIDEBAR TOGGLES ----------------------------
demo_default = os.getenv("DEMO_ARTIFACTS", "0").strip().lower() in {"1", "true", "yes", "on"}
demo_enabled = st.sidebar.checkbox("🧪 Enable Demo Artifacts (synthetic)", value=demo_default,
                                   help="Adds portable, synthetic artifacts & ZIP for filings/demos. Never uses PHI.")

st.sidebar.caption("Tip: set environment variable DEMO_ARTIFACTS=1 to enable by default.")


# ---------------------------- DATA SOURCE ------------------------------
file = st.file_uploader("CSV file", type=["csv"])
use_mock = st.checkbox('Use mock data (data/mock_recruitment.csv)', value=not bool(file))
df = load_dataset(file, use_mock)

st.subheader("Preview")
st.dataframe(df.head(25), use_container_width=True)

# ----------------------- FAIRNESS SUMMARY (SAFE) -----------------------
st.subheader("Fairness Summary")
if HAS_SUMMARIZE:
    try:
        summary = summarize_fairness(df)  # your function
        st.write(summary)
    except Exception as e:
        st.warning(f"Could not compute fairness summary with your current function: {e}")
        st.caption("Ensure src/fairness.summarize_fairness(df) matches expected schema.")
else:
    st.info("summarize_fairness not available. Skipping computation. (Import from src.fairness to enable.)")


# --------------------------- DEMO ARTIFACTS ----------------------------
if demo_enabled:
    st.divider()
    with st.expander("🧪 Demo artifacts (synthetic, illustrative, non-limiting) — click to open", expanded=False):
        st.caption("These examples are synthetic and for demonstration/patent exhibit purposes only. No PHI.")

        csv_bytes = make_input_csv_bytes()
        thr_bytes = make_thresholds_json_bytes()
        artifact_bytes = make_artifact_json_bytes()
        docref_bytes = make_fhir_docref_bytes()
        log_line = make_audit_log_line(prev_hash="GENESIS", artifact_bytes=artifact_bytes)
        summary_text = transparency_summary_text().encode("utf-8")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button("⬇️ input_example.csv", data=csv_bytes,
                               file_name="input_example.csv", mime="text/csv")
            st.download_button("⬇️ thresholds.json", data=thr_bytes,
                               file_name="thresholds.json", mime="application/json")
        with c2:
            st.download_button("⬇️ equity_audit_RS-2025-001_2025Q2.json",
                               data=artifact_bytes,
                               file_name="equity_audit_RS-2025-001_2025Q2.json",
                               mime="application/json")
            st.download_button("⬇️ DocumentReference_RS-2025-001_2025Q2.json",
                               data=docref_bytes,
                               file_name="DocumentReference_RS-2025-001_2025Q2.json",
                               mime="application/json")
        with c3:
            st.download_button("⬇️ audit_log.jsonl (single line)",
                               data=log_line,
                               file_name="audit_log.jsonl",
                               mime="application/json")
            st.text_area("Transparency summary (copy/paste)",
                         value=transparency_summary_text(), height=160)

        # One-click ZIP
        zip_bytes = make_zip_bytes({
            "input_example.csv": csv_bytes,
            "thresholds.json": thr_bytes,
            "equity_audit_RS-2025-001_2025Q2.json": artifact_bytes,
            "DocumentReference_RS-2025-001_2025Q2.json": docref_bytes,
            "audit_log.jsonl": log_line,
            "transparency_summary.txt": summary_text,
        })
        st.download_button("⬇️ Download all demo artifacts (ZIP)",
                           data=zip_bytes,
                           file_name="patent-demo-artifacts.zip",
                           mime="application/zip")

        st.caption(
            "Label these as *Illustrative, non-limiting examples*. "
            "Artifacts demonstrate practical application (§101) and enablement (§112) in filings."
        )

# --------------------------- FOOTER NOTES ------------------------------
st.divider()
st.caption(
    "This interface is for bias & equity auditing in trial recruitment. "
    "Demo artifacts are synthetic. For production, ensure privacy, role-based access, and audit logging."
)
