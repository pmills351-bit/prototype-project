# app_streamlit_audit.py
from typing import List, Optional, Dict, Any
import io, os, json, glob, base64
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from src.fairness import summarize_fairness, format_group_table_for_display
from src.metrics import brier_score, reliability_table
from src.validation import clean_and_validate
from src import config
from src.report_docx import build_docx_report  # requires python-docx

APP_BUILD = "audit-app v3.2 (validation + advanced metrics + LENIENT parity + reports + compare)"

# ------------------------------
# Page & Intro
# ------------------------------
st.set_page_config(page_title="Bias & Equity Audit", layout="wide")
st.title("Bias & Equity Audit for Trial Recruitment")
st.caption(APP_BUILD)

with st.expander("Data requirements & tips", expanded=False):
    st.markdown(
        """
**Required**
- ≥1 **group column** (e.g., `race`, `ethnicity`, `sex`)
- **Binary outcome** column (0/1)

**Normalization**
- Outcome auto-maps `yes/no`, `true/false`, `"1"/"0"` to 0/1.
- Rows missing any selected group or the outcome are excluded.

**Intersectionality**
- Select multiple group columns to analyze `colA × colB`.
"""
    )

tab_audit, tab_compare = st.tabs(["🔎 Audit", "↔️ Compare Runs"])

# ------------------------------
# AUDIT TAB
# ------------------------------
with tab_audit:
    file = st.file_uploader("Upload CSV", type=["csv"])
    use_mock = st.checkbox("Use mock data (data/mock_recruitment.csv)", value=not bool(file))

    if use_mock:
        try:
            df = pd.read_csv("data/mock_recruitment.csv")
        except FileNotFoundError:
            st.error("mock_recruitment.csv not found. Place a CSV at data/mock_recruitment.csv or upload a file.")
            st.stop()
    else:
        if file is None:
            st.info('Upload a CSV or check "Use mock data" to proceed.')
            st.stop()
        df = pd.read_csv(file)

    st.success(f"Loaded {len(df):,} rows")
    with st.expander("Raw data preview (first 100 rows)"):
        st.dataframe(df.head(100), use_container_width=True)

    all_cols = list(df.columns)
    likely_group_cols = [c for c in ["race", "ethnicity", "sex"] if c in all_cols]
    likely_outcome = "selected" if "selected" in all_cols else ("eligible" if "eligible" in all_cols else (all_cols[0] if all_cols else None))
    prob_col = "p_selected" if "p_selected" in all_cols else None

    st.sidebar.header("Audit settings")
    group_cols: List[str] = st.sidebar.multiselect(
        "Group by (choose one or more)",
        options=all_cols,
        default=likely_group_cols or (all_cols[:1] if all_cols else []),
        help="Selecting multiple creates intersectional groups (e.g., race × sex).",
    )

    # Category filters
    MISSING_TOKEN = "〈missing〉"
    filters: Dict[str, set] = {}
    if group_cols:
        st.sidebar.subheader("Category filters")
        for col in group_cols:
            vals = (
                df[col]
                .astype(str)
                .replace({"nan": MISSING_TOKEN})
                .fillna(MISSING_TOKEN)
            )
            options = sorted(vals.unique().tolist())
            selected = st.sidebar.multiselect(f"{col} values", options=options, default=options)
            filters[col] = set(selected)

    outcome_col: Optional[str] = None
    if all_cols:
        default_idx = all_cols.index(likely_outcome) if (likely_outcome in all_cols) else 0
        outcome_col = st.sidebar.selectbox("Outcome column (0/1)", all_cols, index=default_idx)

    ref_strategy = st.sidebar.selectbox(
        "Reference group strategy",
        options=["largest_n", "max_rate", "min_rate", "custom"],
        index=0,
    )

    custom_ref_value = None
    if ref_strategy == "custom":
        if len(group_cols) != 1:
            st.sidebar.warning("Custom reference requires exactly one group column.")
        else:
            unique_vals = sorted(df[group_cols[0]].dropna().astype(str).unique().tolist())
            custom_ref_value = st.sidebar.selectbox("Choose reference value", unique_vals)

    lower = st.sidebar.number_input("Parity lower threshold", value=float(config.LOWER), step=0.01)
    upper = st.sidebar.number_input("Parity upper threshold", value=float(config.UPPER), step=0.01)
    B = st.sidebar.number_input("Bootstrap reps (disparity CI)", min_value=200, max_value=20000, value=int(config.BOOTSTRAP_B), step=200)
    seed = st.sidebar.number_input("Random seed", value=int(config.SEED), step=1)
    show_counts = st.sidebar.checkbox("Show counts (n, successes)", value=True)

    # Strict/Lenient toggles
    strict_parity = st.sidebar.checkbox(
        "Stricter parity (fallback to point estimate when CI is wide)",
        value=True,
        help="If CI is very wide and the point estimate is outside thresholds, mark Fail instead of Borderline.",
    )
    wide_ci_thresh = st.sidebar.number_input("Wide CI threshold (hi − lo)", min_value=0.05, max_value=2.0, step=0.05, value=0.5)

    lenient_parity = st.sidebar.checkbox(
        "Lenient parity (Pass if point estimate within thresholds)",
        value=False,
        help="Clinician-friendly: ignores CI overlap when disparity point estimate is within [lower, upper].",
    )

    # Advanced metrics toggle (table columns only)
    show_advanced = st.sidebar.checkbox("Show advanced metrics (risk diff, relative risk, parity diff)", value=True)

    # Apply category filters
    work_df = df.copy()
    if group_cols:
        for col in group_cols:
            allowed = filters.get(col)
            if allowed is None:
                continue
            mask = (
                work_df[col]
                .astype(str)
                .replace({"nan": MISSING_TOKEN})
                .fillna(MISSING_TOKEN)
                .isin(allowed)
            )
            work_df = work_df[mask]

    rows_before = len(df); rows_after_filter = len(work_df)

    # Clean + validate
    if not group_cols or outcome_col is None:
        st.warning("Choose group column(s) and outcome to proceed.")
        st.stop()

    from src.validation import clean_and_validate
    clean_df, report = clean_and_validate(work_df, group_cols, outcome_col, drop_na_rows=True, missing_token=MISSING_TOKEN)
    if not report["required_present"]:
        st.error(f"Missing required columns: {report['missing_required']}")
        st.stop()

    rows_after_clean = len(clean_df)
    with st.expander("Data diagnostics"):
        st.markdown(
            f"""
- Rows before filters: **{rows_before:,}**
- Rows after category filters: **{rows_after_filter:,}**
- Rows after cleaning (drop NA in selected group/outcome): **{rows_after_clean:,}**
- Outcome values coerced: **{report['coerced_outcome_count']}**
- Remaining non-binary outcome values (dropped): **{report['nonbinary_outcome_after_coercion']}**
"""
        )
        st.markdown("**Distinct values (selected group columns):**")
        st.json(report["distinct_values"])

    # Run audit
    with st.spinner("Computing fairness metrics..."):
        result = summarize_fairness(
            df=clean_df,
            group_cols=group_cols,
            outcome_col=outcome_col,
            ref_strategy=ref_strategy,
            custom_ref_value=custom_ref_value,
            lower=lower,
            upper=upper,
            B=int(B),
            seed=int(seed),
            use_point_fallback=bool(strict_parity),
            wide_ci_threshold=float(wide_ci_thresh),
            lenient_parity=bool(lenient_parity),   # NEW
        )

    display_df = format_group_table_for_display(result, show_counts=show_counts)

    # Optionally hide advanced metric columns
    if not show_advanced:
        keep = [c for c in display_df.columns if c not in {
            "risk difference [95% CI]",
            "relative risk [95% CI]",
            "parity difference (ref − grp) [95% CI]",
        }]
        display_df = display_df[keep]

    st.subheader("Group / Intersectional Summary")
    with st.expander("How to read this table", expanded=True):
        st.markdown(
            """
- **selection rate [95% CI]**: successes ÷ n (Wilson CI).
- **disparity [95% CI]**: group rate ÷ reference rate (1.0 = equal).
- **risk difference [95% CI]**: group rate − reference rate (points).
- **relative risk [95% CI]**: same as disparity (redundant; shown for completeness).
- **parity difference [95% CI]**: reference rate − group rate (points).
- **parity** flag (default strict): CI vs thresholds; **Stricter parity** converts wide-CI borderline to Fail when point estimate is outside.
- **Lenient parity** (optional): **Pass** when point estimate is within thresholds, even if CI overlaps.
"""
        )

    # Color parity cell
    if "parity" in display_df.columns:
        raw_parity = display_df["parity"].copy()
        def parity_badge(x: str) -> str:
            if x == "Fail": return "❌ Fail"
            if x == "Borderline": return "⚠️ Borderline"
            if x == "Pass": return "✅ Pass"
            return x
        display_df["parity"] = display_df["parity"].map(parity_badge)
    else:
        raw_parity = pd.Series([""] * len(display_df))

    def style_parity(df_in: pd.DataFrame):
        styles = pd.DataFrame("", index=df_in.index, columns=df_in.columns)
        for idx in df_in.index:
            val = raw_parity.iloc[idx] if len(raw_parity) == len(df_in) else ""
            badge = str(df_in.loc[idx, "parity"]) if "parity" in df_in.columns else ""
            status = val or ("Fail" if "Fail" in badge else ("Borderline" if "Borderline" in badge else ("Pass" if "Pass" in badge else "")))
            if status == "Fail":
                styles.loc[idx, "parity"] = "background-color: #fdecea"
            elif status == "Borderline":
                styles.loc[idx, "parity"] = "background-color: #fff4e5"
            elif status == "Pass":
                styles.loc[idx, "parity"] = "background-color: #e6f4ea"
        return styles

    styled = display_df.style.apply(style_parity, axis=None)
    try:
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        try:
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        except TypeError:
            st.dataframe(display_df, use_container_width=True)

    # Calibration (optional)
    bs = None
    report_plot_png_b64 = None
    if prob_col and prob_col in clean_df.columns:
        st.subheader("Calibration (optional)")
        st.markdown("Compute **Brier score** and show a **reliability diagram** if a probability column is present.")
        bs = brier_score(clean_df[outcome_col], clean_df[prob_col])
        st.metric("Brier score", f"{bs:.3f}" if np.isfinite(bs) else "N/A")

        rel = reliability_table(clean_df[outcome_col], clean_df[prob_col], bins=10, strategy="quantile")
        if not rel.empty:
            import matplotlib.pyplot as plt
            fig = plt.figure()
            plt.plot(rel["p_mean"], rel["y_rate"], marker="o")
            plt.plot([0, 1], [0, 1], linestyle="--")
            plt.xlabel("Mean predicted probability")
            plt.ylabel("Observed selection rate")
            plt.title("Reliability Diagram")
            st.pyplot(fig)

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight")
            buf.seek(0)
            report_plot_png_b64 = base64.b64encode(buf.read()).decode("ascii")
            buf.close()
        else:
            st.info("Not enough probability diversity to compute a reliability diagram.")

# Exports
col1, col2 = st.columns(2)
with col1:
    csv_bytes = display_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download summary table (CSV)", data=csv_bytes, file_name="audit_summary.csv", mime="text/csv")

with col2:
    from src.report_docx import build_docx_report_bytes, MIME_DOCX
    if st.button("Prepare report (DOCX)"):
        # Build once and stash in session so we can download immediately
        st.session_state["report_buf"] = build_docx_report_bytes(
            app_build=APP_BUILD,
            settings=dict(
                group_cols=group_cols, outcome_col=outcome_col, ref_strategy=ref_strategy,
                custom_ref_value=custom_ref_value, lower=float(lower), upper=float(upper),
                B=int(B), seed=int(seed), strict_parity=bool(strict_parity),
                lenient_parity=bool(lenient_parity),
                wide_ci_thresh=float(wide_ci_thresh),
                rows_before=int(rows_before), rows_after=int(rows_after_clean),
            ),
            table_df=display_df,
            calibration_png_b64=report_plot_png_b64,
            brier=float(bs) if bs is not None and np.isfinite(bs) else None,
        )
        st.success("Report ready. Click the download button below ⤵")

    if "report_buf" in st.session_state:
        st.download_button(
            "Download report (DOCX)",
            data=st.session_state["report_buf"].getvalue(),
            file_name="audit_report.docx",
            mime=MIME_DOCX,
        )


    # Save run
    st.subheader("Save Run")
    if st.button("Save current run"):
        os.makedirs("runs", exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run = {
            "ts": ts,
            "app_build": APP_BUILD,
            "settings": dict(
                group_cols=group_cols, outcome_col=outcome_col, ref_strategy=ref_strategy,
                custom_ref_value=custom_ref_value, lower=float(lower), upper=float(upper),
                B=int(B), seed=int(seed), strict_parity=bool(strict_parity),
                lenient_parity=bool(lenient_parity),
                wide_ci_thresh=float(wide_ci_thresh),
                rows_before=int(rows_before), rows_after=int(rows_after_clean),
            ),
            "summary": display_df.to_dict(orient="records"),
        }
        json_path = f"runs/run_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(run, f, indent=2)
        st.success(f"Saved: {json_path}")

# ------------------------------
# COMPARE TAB
# ------------------------------
with tab_compare:
    st.subheader("Compare Saved Runs")
    run_files = sorted(glob.glob("runs/run_*.json"))
    if not run_files:
        st.info("No saved runs found. Create one in the Audit tab.")
    else:
        col_r1, col_r2 = st.columns(2)
        run1 = col_r1.selectbox("Run A", run_files, index=max(0, len(run_files)-2))
        run2 = col_r2.selectbox("Run B", run_files, index=max(0, len(run_files)-1))

        def load_run(path: str) -> Dict[str, Any]:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        if run1 and run2 and run1 != run2:
            r1 = load_run(run1); r2 = load_run(run2)
            st.markdown("**Settings A**"); st.json(r1.get("settings", {}))
            st.markdown("**Settings B**"); st.json(r2.get("settings", {}))

            df1 = pd.DataFrame(r1.get("summary", []))
            df2 = pd.DataFrame(r2.get("summary", []))

            group_like_cols = [c for c in df1.columns if c not in {
                "n","successes","ref","selection rate [95% CI]","disparity [95% CI]",
                "parity","risk difference [95% CI]","relative risk [95% CI]","parity difference (ref − grp) [95% CI]"
            }]
            if not group_like_cols:
                st.error("Cannot align runs (no obvious group columns).")
            else:
                def first_float(s: str) -> float:
                    try: return float(str(s).split(" ", 1)[0])
                    except Exception: return np.nan

                for dfx in (df1, df2):
                    dfx["rate_val"] = dfx["selection rate [95% CI]"].map(first_float)
                    dfx["disp_val"] = dfx["disparity [95% CI]"].map(first_float)

                left = df1[group_like_cols + ["rate_val","disp_val","parity"]].rename(
                    columns={"rate_val":"rate_A","disp_val":"disp_A","parity":"parity_A"}
                )
                right = df2[group_like_cols + ["rate_val","disp_val","parity"]].rename(
                    columns={"rate_val":"rate_B","disp_val":"disp_B","parity":"parity_B"}
                )
                merged = pd.merge(left, right, on=group_like_cols, how="outer")
                merged["Δrate"] = merged["rate_B"] - merged["rate_A"]
                merged["Δdisp"] = merged["disp_B"] - merged["disp_A"]
                def change(a,b):
                    a=str(a); b=str(b); return "→".join([a,b]) if a!=b else a
                merged["parity_change"] = [change(a,b) for a,b in zip(merged["parity_A"], merged["parity_B"])]

                show = group_like_cols + ["rate_A","rate_B","Δrate","disp_A","disp_B","Δdisp","parity_A","parity_B","parity_change"]
                st.dataframe(merged[show], use_container_width=True)
                st.download_button("Download comparison CSV", merged[show].to_csv(index=False).encode("utf-8"), "audit_compare_runs.csv", "text/csv")
# --- Combined DOCX export for Compare tab ---
from src.report_docx import build_docx_compare_bytes, MIME_DOCX

runA_title = os.path.basename(run1)
runB_title = os.path.basename(run2)

# Key columns are the non-metric group columns detected above
key_cols = group_like_cols

docx_cmp = build_docx_compare_bytes(
    app_build=APP_BUILD,
    runA_title=runA_title,
    runB_title=runB_title,
    settingsA=r1.get("settings", {}),
    settingsB=r2.get("settings", {}),
    key_cols=key_cols,
    merged_df=merged[show],  # same columns you display
)

st.download_button(
    "Download combined report (DOCX)",
    data=docx_cmp.getvalue(),
    file_name="audit_compare_report.docx",
    mime=MIME_DOCX,
)
# --- end combined export ---






