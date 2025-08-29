"""
EquiEnroll — Pilot Streamlit App (adds Compliance Exports section).
Run: streamlit run app_streamlit_audit_pilot.py
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from datetime import date
from trial_equity import ExportBuilder, ExportContext
from trial_equity.cli import build_dap_from_csv

st.set_page_config(page_title="EquiEnroll — Trial Equity Audit", layout="wide")
st.title("EquiEnroll — Trial Equity Audit")
st.caption("Inclusive enrollment you can measure.")

st.markdown("Upload a CSV with columns: **race, ethnicity, sex, age, eligible, contacted, selected**")

file = st.file_uploader("CSV file", type=["csv"])
use_mock = st.checkbox("Use mock data (data/mock_recruitment.csv)", value=not bool(file))

# Load data
if use_mock:
    try:
        df = pd.read_csv("data/mock_recruitment.csv")
        src_path = "data/mock_recruitment.csv"
    except FileNotFoundError:
        st.error("mock_recruitment.csv not found.")
        st.stop()
else:
    if file is None:
        st.info("Upload a CSV or check 'Use mock data' to proceed.")
        st.stop()
    df = pd.read_csv(file)
    src_path = "uploaded.csv"
    df.to_csv(src_path, index=False)

st.subheader("Preview")
st.dataframe(df.head(50))

st.markdown("---")
st.header("Compliance Exports (v1)")
col1, col2, col3 = st.columns(3)
with col1:
    study_id = st.text_input("Study ID", value="ABC-123")
with col2:
    data_cut = st.date_input("Data cut date", value=date.today())
with col3:
    out_dir = st.text_input("Output folder", value="out")

if st.button("Generate DAP Packet + HTI-1 Card + Audit Pack"):
    ctx = ExportContext(study_id=study_id, data_cut=str(data_cut), out_dir=out_dir)
    eb = ExportBuilder(ctx)

    # DAP from CSV
    dap_payload = build_dap_from_csv(Path(src_path))
    p1 = eb.build_dap_packet(dap_payload)

    # Basic HTI-1 card
    card = {
        "artifact_id":"EquiEnroll-TransparencyCard",
        "intended_use":"Recruitment fairness analytics for clinical trials",
        "inputs":["race","ethnicity","sex","age","eligible","contacted","selected"],
        "logic_summary":"Parity gaps + Wilson CIs; action queues for under-reached groups",
        "performance":[],
        "limitations":["Small-n instability in rare subgroups"],
        "irm":{"risks":["missing race"],"mitigations":["guardrails"],"monitoring":"quarterly fairness check"},
        "version": ctx.version
    }
    p2 = eb.build_transparency_card(card)
    z = eb.build_audit_pack()

    st.success("Exports created.")
    st.write("DAP packet:", p1)
    st.write("Transparency card:", p2)
    st.write("Audit pack:", z)
