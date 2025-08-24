# Streamlit UI (thin) — uses the trial_equity package for all logic.
# Run: streamlit run app_streamlit.py

import io
import yaml
import pandas as pd
import streamlit as st

from trial_equity.normalize import normalize_race, normalize_eth, normalize_sex
from trial_equity.io_utils import parse_dt, years_between
from trial_equity.mapping_runtime import apply_mapping, load_mapping
from trial_equity.schema import validate_canonical_v1 as validate_canonical_v1_inline
from trial_equity.metrics import group_rate_ci, wilson_ci
# -------------------------------------------------------------------
# Pretty display for metric tables: show "—" when value is NaN; round others
# -------------------------------------------------------------------
def _format_metrics_display(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["rate", "ci_low", "ci_high"]:
        if col in out.columns:
            out[col] = out[col].apply(lambda x: "—" if pd.isna(x) else f"{x:.3f}")
    return out

st.set_page_config(page_title="Trial Equity • Canonical + Audit", layout="wide")

# -------------------------------------------------------------------
# Excel safety helper: strip timezone info (Excel doesn't support tz-aware datetimes)
# -------------------------------------------------------------------
def make_excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        # tz-aware datetime column -> drop tz
        if pd.api.types.is_datetime64tz_dtype(out[col]):
            out[col] = out[col].dt.tz_convert(None)
        # object column: try parse ISO timestamps with Z/+00:00, then drop tz
        elif out[col].dtype == "object":
            try:
                coerced = pd.to_datetime(out[col], errors="coerce", utc=True)
                if pd.api.types.is_datetime64tz_dtype(coerced):
                    coerced = coerced.dt.tz_convert(None)
                # only replace if we actually parsed at least one timestamp
                if coerced.notna().any():
                    out[col] = coerced
            except Exception:
                pass
    return out

# -------------------------------------------------------------------
# Default mapping YAML shown in the UI (edit or upload your own)
# -------------------------------------------------------------------
DEFAULT_MAPPING_YAML = """\
version: 1
schema_version: "1.0.0"
assign:
  site_id: "SITE_X"
  trial_id: "NCT01234567"
columns:
  patient_id: "hash(SALT, row['MRN'])"
  race: "normalize_race(row['RACE_DESC'])"
  ethnicity: "normalize_eth(row['ETHNICITY'])"
  sex: "normalize_sex(row['SEX'])"
  age: "years_between(row['BIRTH_DATE'], row['MATCH_DATE'])"
  eligible: "int(row['MATCH_FLAG'])"
  selected: "int(row['CONTACTED'])"
  identified: "int(row['IDENTIFIED'])"
  contacted: "int(row['CONTACTED'])"
  consented: "int(row['CONSENTED'])"
  enrolled: "int(row['ENROLLED'])"
  identified_at: "parse_dt(row['IDENTIFIED_AT'])"
  contacted_at: "parse_dt(row['CONTACTED_AT'])"
  match_score: "float(row['SCORE'])"
  matched_criteria: "str(row['CRITERIA_JSON'])"
provenance:
  source_system: "demo_csv"
"""

# -------------------------------------------------------------------
# Optional small-cell suppression (privacy) used for downloads
# -------------------------------------------------------------------
def small_cell_suppress(df: pd.DataFrame, group_cols, threshold: int = 11) -> pd.DataFrame:
    if not group_cols:
        return df.copy()
    counts = df.groupby(list(group_cols)).size().reset_index(name="_n")
    small = counts[counts["_n"] < threshold]
    if small.empty:
        return df.copy()
    key = list(group_cols)
    suppressed = df.merge(small[key], on=key, how="left", indicator=True)
    return suppressed[suppressed["_merge"] == "left_only"].drop(columns=["_merge"])

# -------------------------------------------------------------------
# UI
# -------------------------------------------------------------------
st.title("Trial Equity – Canonical v1 + Fairness Audit")
tab_ingest, tab_audit = st.tabs(["📥 Ingest & Map (Canonical v1)", "⚖️ Fairness Audit"])

# -------------------------- Ingest & Map ---------------------------
with tab_ingest:
    st.subheader("Upload source data and map to Canonical v1")

    data_file = st.file_uploader("Upload data (.csv or .xlsx)", type=["csv", "xlsx", "xls"], key="ingest_file")
    salt = st.text_input("Site salt for hashing IDs", value="MY_SITE_SALT", key="salt")
    st.caption("Use a site-specific secret to pseudonymize patient IDs (e.g., per-site BAA/DUA).")

    st.markdown("**Mapping YAML** (edit here or upload a .yaml)")
    mapping_source = st.radio("Provide mapping via:", ["Text area", "Upload .yaml"], index=0, key="map_source")

    if mapping_source == "Upload .yaml":
        mapping_upload = st.file_uploader("Upload mapping YAML", type=["yaml", "yml"], key="yaml_up")
        mapping_yaml_text = DEFAULT_MAPPING_YAML if mapping_upload is None else mapping_upload.read().decode("utf-8")
    else:
        mapping_yaml_text = st.text_area("Mapping YAML", value=DEFAULT_MAPPING_YAML, height=320, key="yaml_text")

    if st.button("Run Mapping → Validate", type="primary", key="run_map"):
        if data_file is None:
            st.error("Please upload a CSV/XLSX file.")
            st.stop()

        # Read input
        try:
            if data_file.name.lower().endswith(".csv"):
                df_in = pd.read_csv(data_file)
            else:
                df_in = pd.read_excel(data_file)
        except Exception as e:
            st.error(f"Failed to read file: {e}")
            st.stop()

        # Load mapping
        try:
            mapping = yaml.safe_load(mapping_yaml_text)
        except Exception as e:
            st.error(f"Invalid YAML: {e}")
            st.stop()

        # Map to canonical
        try:
            df_out = apply_mapping(df_in, mapping, default_site_salt=salt)
        except Exception as e:
            st.error(f"Mapping failed: {e}")
            st.stop()

        # Coerce 0/1 flags and age numeric
        for col in ["eligible", "selected", "identified", "contacted", "consented", "enrolled"]:
            if col in df_out.columns:
                df_out[col] = pd.to_numeric(df_out[col], errors="coerce").fillna(0).astype(int)
        if "age" in df_out.columns:
            df_out["age"] = pd.to_numeric(df_out["age"], errors="coerce")

        # Normalize enums
        if "race" in df_out.columns:
            df_out["race"] = df_out["race"].apply(normalize_race)
        if "ethnicity" in df_out.columns:
            df_out["ethnicity"] = df_out["ethnicity"].apply(normalize_eth)
        if "sex" in df_out.columns:
            df_out["sex"] = df_out["sex"].apply(normalize_sex)

        # Validate canonical v1
        try:
            validate_canonical_v1_inline(df_out)
            st.success("✅ Canonical v1 validation passed.")
        except Exception as e:
            st.error(f"Canonical v1 validation failed: {e}")
            st.stop()

        # Save to session and show preview
        st.session_state["canonical_df"] = df_out
        st.write("**Preview (first 100 rows):**")
        st.dataframe(df_out.head(100), use_container_width=True)

        # Privacy options + downloads
        st.markdown("**Privacy options for downloads**")
        suppress = st.checkbox("Apply small-cell suppression to downloads", value=False, key="suppress")
        group_cols = st.multiselect(
            "Suppress by grouping columns",
            options=list(df_out.columns),
            default=["race", "ethnicity", "sex"],
            key="grpcols",
        )
        threshold = st.number_input("Suppression threshold", min_value=2, max_value=50, value=11, key="thr")

        df_export = df_out.copy()
        if suppress and group_cols:
            df_export = small_cell_suppress(df_export, group_cols=group_cols, threshold=int(threshold))

        # CSV download
        csv_bytes = df_export.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download Canonical CSV", data=csv_bytes, file_name="canonical_v1.csv", mime="text/csv", key="dl_csv")

        # Excel download (timezone-safe)
        df_xlsx = make_excel_safe(df_export)
        with io.BytesIO() as buf:
            with pd.ExcelWriter(buf, engine="openpyxl") as xlw:
                df_xlsx.to_excel(xlw, index=False, sheet_name="Data")
            xlsx_bytes = buf.getvalue()
        st.download_button(
            "⬇️ Download Canonical Excel",
            data=xlsx_bytes,
            file_name="canonical_v1.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_xlsx",
        )

        st.info("Next: switch to the **Fairness Audit** tab to run metrics on this canonical dataset.")

# -------------------------- Fairness Audit -------------------------
with tab_audit:
    st.subheader("Run fairness metrics on Canonical v1")

    if "canonical_df" not in st.session_state:
        st.warning("No canonical dataset in memory yet. Go to the **Ingest & Map** tab and run mapping first.")
    else:
        df = st.session_state["canonical_df"].copy()

        # Ensure binary columns are clean ints (0/1) so denominators/numerators behave
        for col in ["eligible", "contacted", "consented", "enrolled"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # Group choice
        group_col = st.selectbox("Group by", options=["race", "ethnicity", "sex", "site_id"], index=0)

        # ---------- Representation ----------
        st.write("### Representation")
        idf = df[df.get("identified", 1) == 1].copy() if "identified" in df.columns else df.copy()
        rep = idf[group_col].value_counts(dropna=False).rename_axis(group_col).reset_index(name="n")
        rep["share"] = rep["n"] / rep["n"].sum() if rep["n"].sum() else 0
        st.dataframe(rep, use_container_width=True)

        # ---------- Selection Parity: Contacted | Eligible ----------
        st.write("### Selection Parity (Contacted | Eligible)")
        if {"eligible", "contacted"}.issubset(df.columns):
            sel = group_rate_ci(df, group_col=group_col, num_col="contacted", den_cond_col="eligible")
            st.dataframe(_format_metrics_display(sel), use_container_width=True)
        else:
            st.info("Need `eligible` and `contacted` columns for this metric.")

        # ---------- Opportunity Parity: Consented | Contacted ----------
        st.write("### Opportunity Parity (Consented | Contacted)")
        if {"contacted", "consented"}.issubset(df.columns):
            opp = group_rate_ci(df, group_col=group_col, num_col="consented", den_cond_col="contacted")
            st.dataframe(_format_metrics_display(opp), use_container_width=True)
        else:
            st.info("Need `contacted` and `consented` columns for this metric.")

        # ---------- Enrollment: Enrolled | Consented ----------
        st.write("### Enrollment (Enrolled | Consented)")
        if {"consented", "enrolled"}.issubset(df.columns):
            enr = group_rate_ci(df, group_col=group_col, num_col="enrolled", den_cond_col="consented")
            st.dataframe(_format_metrics_display(enr), use_container_width=True)
        else:
            st.info("Need `consented` and `enrolled` columns for this metric.")
                    # ---------- Risk Ratios vs reference group ----------
        st.write("### Risk Ratios vs Reference Group")
        with st.expander("Show risk ratios (RR)"):
            # Choose metric and reference group value
            rr_metric = st.selectbox("Metric", options=["selection", "opportunity", "enrollment"], index=0,
                                     help="selection=Contacted|Eligible, opportunity=Consented|Contacted, enrollment=Enrolled|Consented")
            # reference group choices from current data
            ref_options = sorted(df[group_col].dropna().astype(str).unique().tolist())
            default_ref = "White" if "White" in ref_options else (ref_options[0] if ref_options else "")
            ref_val = st.selectbox("Reference group value", options=ref_options, index=ref_options.index(default_ref) if default_ref in ref_options else 0)

            if rr_metric == "selection":
                num, den, title = "contacted", "eligible", "Risk Ratios (Contacted | Eligible)"
            elif rr_metric == "opportunity":
                num, den, title = "consented", "contacted", "Risk Ratios (Consented | Contacted)"
            else:
                num, den, title = "enrolled", "consented", "Risk Ratios (Enrolled | Consented)"

            try:
                from trial_equity.metrics import group_rr as _group_rr
                rr_df = _group_rr(df, group_col=group_col, num_col=num, den_cond_col=den, ref_value=ref_val)
                # pretty display
                show = rr_df[[group_col, "n_denom", "n_num", "rate", "rr", "rr_low", "rr_high"]].copy()
                for col in ["rate", "rr", "rr_low", "rr_high"]:
                    show[col] = show[col].apply(lambda x: "—" if pd.isna(x) else f"{x:.3f}")
                st.write(f"**{title} by {group_col} vs {ref_val}**")
                st.dataframe(show, use_container_width=True)
                st.caption("RR compares each group's rate to the reference group's rate (RR=1 is parity). “—” indicates undefined due to a zero denominator.")
            except Exception as e:
                st.info(f"Unable to compute RR: {e}")


        st.caption("Confidence intervals use the Wilson method. “—” indicates an undefined value because the denominator is 0.")
