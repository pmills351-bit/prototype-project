# trial_equity/cli.py
# Usage examples:
#   te map --in data/input/sample_input_rich.csv --map data/mappings/mapping_demo.yaml --salt MY_SITE_SALT --out out/canonical.csv
#   te validate --in out/canonical.csv
#   te audit --in out/canonical.csv --group race --metric selection --age-min 40 --sex Female --from 2025-08-01 --to 2025-08-31
#   te rr --in out/canonical.csv --group race --metric selection --ref "White" --race "Black or African American,White" --out out/rr_selection_by_race.csv

from __future__ import annotations
import sys, argparse, io
from pathlib import Path
from datetime import datetime
import pandas as pd

from trial_equity.mapping_runtime import apply_mapping, load_mapping
from trial_equity.normalize import normalize_race, normalize_eth, normalize_sex
from trial_equity.schema import validate_canonical_v1
from trial_equity.metrics import group_rate_ci, group_rr

# ---------------- Basic IO helpers ----------------
def _read_table(path: Path) -> pd.DataFrame:
    p = str(path).lower()
    if p.endswith(".csv"):
        return pd.read_csv(path)
    elif p.endswith(".xlsx") or p.endswith(".xls"):
        return pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {path}")

def _write_table(df: pd.DataFrame, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    low = str(out_path).lower()
    if low.endswith(".csv"):
        df.to_csv(out_path, index=False)
    elif low.endswith((".xlsx", ".xls")):
        # Excel can't store tz-aware datetimes; strip tz
        df_x = df.copy()
        for col in df_x.columns:
            if pd.api.types.is_datetime64tz_dtype(df_x[col]):
                df_x[col] = df_x[col].dt.tz_convert(None)
        with pd.ExcelWriter(out_path, engine="openpyxl") as xlw:
            df_x.to_excel(xlw, index=False, sheet_name="Data")
    else:
        raise ValueError("Output must be .csv or .xlsx")

def _coerce_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["eligible","selected","identified","contacted","consented","enrolled"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)
    if "age" in out.columns:
        out["age"] = pd.to_numeric(out["age"], errors="coerce")
    return out

# ---------------- Filters ----------------
def _parse_date(s: str | None):
    if not s:
        return None
    # Accept YYYY-MM-DD
    return pd.to_datetime(s, errors="coerce")

def _choose_datetime_col(df: pd.DataFrame) -> str | None:
    for c in ["identified_at", "contacted_at"]:
        if c in df.columns:
            return c
    return None

def _apply_filters(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    out = df.copy()

    # Age
    if "age" in out.columns:
        if args.age_min is not None:
            out = out[out["age"] >= float(args.age_min)]
        if args.age_max is not None:
            out = out[out["age"] <= float(args.age_max)]

    # Categorical includes: case-insensitive, multi-value comma-separated
    def _filter_in(col: str, val: str | None):
        nonlocal out
        if val and col in out.columns:
            wanted = [v.strip().lower() for v in val.split(",") if v.strip()]
            out = out[out[col].astype(str).str.lower().isin(wanted)]

    _filter_in("sex", args.sex)
    _filter_in("race", args.race)
    _filter_in("ethnicity", args.ethnicity)
    _filter_in("site_id", args.site)

    # Date range on identified_at (preferred) or contacted_at
    dt_col = _choose_datetime_col(out)
    if dt_col:
        out[dt_col] = pd.to_datetime(out[dt_col], errors="coerce", utc=True)
        dfrom = _parse_date(args.date_from)
        dto   = _parse_date(args.date_to)
        if dfrom is not None:
            if dfrom.tzinfo is None:
                dfrom = dfrom.tz_localize("UTC")
            out = out[out[dt_col] >= dfrom]
        if dto is not None:
            if dto.tzinfo is None:
                dto = dto.tz_localize("UTC")
            upper = dto + pd.Timedelta(days=1)  # inclusive end
            out = out[out[dt_col] < upper]

    return out

def _add_filter_args(p: argparse.ArgumentParser):
    p.add_argument("--age-min", dest="age_min", required=False, help="Minimum age (inclusive)")
    p.add_argument("--age-max", dest="age_max", required=False, help="Maximum age (inclusive)")
    p.add_argument("--sex", dest="sex", required=False, help='Filter sex (e.g., "Female" or "Female,Male")')
    p.add_argument("--race", dest="race", required=False, help='Filter race values (comma-separated)')
    p.add_argument("--ethnicity", dest="ethnicity", required=False, help='Filter ethnicity values (comma-separated)')
    p.add_argument("--site", dest="site", required=False, help='Filter site_id values (comma-separated)')
    p.add_argument("--from", dest="date_from", required=False, help="Start date YYYY-MM-DD (identified_at/contacted_at)")
    p.add_argument("--to", dest="date_to", required=False, help="End date YYYY-MM-DD inclusive")

# ---------------- Commands ----------------
def cmd_map(args: argparse.Namespace) -> int:
    src = Path(args.input)
    mapping_path = Path(args.mapping)
    out_path = Path(args.out) if args.out else None
    salt = args.salt or "MY_SITE_SALT"

    df_in = _read_table(src)
    mapping = load_mapping(str(mapping_path))
    df_out = apply_mapping(df_in, mapping, default_site_salt=salt)

    # normalize + coerce for safety
    if "race" in df_out.columns: df_out["race"] = df_out["race"].apply(normalize_race)
    if "ethnicity" in df_out.columns: df_out["ethnicity"] = df_out["ethnicity"].apply(normalize_eth)
    if "sex" in df_out.columns: df_out["sex"] = df_out["sex"].apply(normalize_sex)
    df_out = _coerce_flags(df_out)

    # validate
    validate_canonical_v1(df_out)

    # write or print head
    if out_path:
        _write_table(df_out, out_path)
        print(f"OK: Mapped + validated. Wrote: {out_path}")
    else:
        buf = io.StringIO()
        df_out.head(20).to_string(buf, index=False)
        print(buf.getvalue())
    return 0

def cmd_validate(args: argparse.Namespace) -> int:
    src = Path(args.input)
    df = _read_table(src)
    try:
        validate_canonical_v1(df)
        print("OK: Canonical v1 validation passed.")
        return 0
    except Exception as e:
        print(f"ERROR: Validation failed: {e}", file=sys.stderr)
        return 2

def _fmt_table(df: pd.DataFrame, cols_fmt=("rate","ci_low","ci_high")) -> pd.DataFrame:
    show = df.copy()
    def fmt(x): return "—" if pd.isna(x) else f"{x:.3f}"
    for c in cols_fmt:
        if c in show.columns:
            show[c] = show[c].apply(fmt)
    return show

def cmd_audit(args: argparse.Namespace) -> int:
    src = Path(args.input)
    group = args.group
    metric = args.metric.lower()
    out_path = Path(args.out) if args.out else None

    df = _read_table(src)
    df = _coerce_flags(df)
    df = _apply_filters(df, args)

    if metric == "selection":
        num, den = "contacted", "eligible"
        title = f"Selection Parity (Contacted | Eligible) by {group}"
    elif metric == "opportunity":
        num, den = "consented", "contacted"
        title = f"Opportunity Parity (Consented | Contacted) by {group}"
    elif metric == "enrollment":
        num, den = "enrolled", "consented"
        title = f"Enrollment (Enrolled | Consented) by {group}"
    else:
        raise ValueError("metric must be one of: selection, opportunity, enrollment")

    res = group_rate_ci(df, group_col=group, num_col=num, den_cond_col=den)

    print(f"\n{title}")
    print("-" * len(title))
    print(_fmt_table(res).to_string(index=False))

    if out_path:
        res.to_csv(out_path, index=False)
        print(f"\nOK: Wrote raw audit table: {out_path}")
    return 0

def cmd_rr(args: argparse.Namespace) -> int:
    src = Path(args.input)
    group = args.group
    metric = args.metric.lower()
    ref = args.ref
    thr = float(args.threshold)
    out_path = Path(args.out) if args.out else None

    df = _read_table(src)
    df = _coerce_flags(df)
    df = _apply_filters(df, args)

    if metric == "selection":
        num, den = "contacted", "eligible"
        title = f"Risk Ratios (Contacted | Eligible) by {group} vs {ref}"
    elif metric == "opportunity":
        num, den = "consented", "contacted"
        title = f"Risk Ratios (Consented | Contacted) by {group} vs {ref}"
    elif metric == "enrollment":
        num, den = "enrolled", "consented"
        title = f"Risk Ratios (Enrolled | Consented) by {group} vs {ref}"
    else:
        raise ValueError("metric must be one of: selection, opportunity, enrollment")

    res = group_rr(df, group_col=group, num_col=num, den_cond_col=den, ref_value=ref)
    out = res.copy()
    out["flag_low"] = out["rr"] < thr

    print(f"\n{title}")
    print("-" * len(title))
    show = out[[group, "n_denom", "n_num", "rate", "rr", "rr_low", "rr_high", "flag_low"]].copy()
    def fmt(x): return "—" if pd.isna(x) else f"{x:.3f}"
    for c in ["rate","rr","rr_low","rr_high"]:
        show[c] = show[c].apply(fmt)
    print(show.to_string(index=False))

    if out_path:
        out.to_csv(out_path, index=False)
        print(f"\nOK: Wrote RR table: {out_path}")
    return 0

# ---------------- Parser + main ----------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="te", description="Trial Equity CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # te map
    p_map = sub.add_parser("map", help="Map source table → Canonical v1 and validate")
    p_map.add_argument("--in", dest="input", required=True, help="Input .csv/.xlsx")
    p_map.add_argument("--map", dest="mapping", required=True, help="Mapping YAML")
    p_map.add_argument("--salt", dest="salt", required=False, help="Site salt for hashing")
    p_map.add_argument("--out", dest="out", required=False, help="Output .csv/.xlsx")
    p_map.set_defaults(func=cmd_map)

    # te validate
    p_val = sub.add_parser("validate", help="Validate an existing Canonical v1 file")
    p_val.add_argument("--in", dest="input", required=True, help="Canonical .csv/.xlsx")
    p_val.set_defaults(func=cmd_validate)

    # te audit
    p_aud = sub.add_parser("audit", help="Compute fairness metrics on Canonical v1")
    p_aud.add_argument("--in", dest="input", required=True, help="Canonical .csv/.xlsx")
    p_aud.add_argument("--group", dest="group", required=True, choices=["race","ethnicity","sex","site_id"])
    p_aud.add_argument("--metric", dest="metric", required=True, choices=["selection","opportunity","enrollment"])
    p_aud.add_argument("--out", dest="out", required=False, help="Write raw audit table to CSV")
    _add_filter_args(p_aud)
    p_aud.set_defaults(func=cmd_audit)

    # te rr
    p_rr = sub.add_parser("rr", help="Risk ratios vs a reference group")
    p_rr.add_argument("--in", dest="input", required=True, help="Canonical .csv/.xlsx")
    p_rr.add_argument("--group", dest="group", required=True, choices=["race","ethnicity","sex","site_id"])
    p_rr.add_argument("--metric", dest="metric", required=True, choices=["selection","opportunity","enrollment"])
    p_rr.add_argument("--ref", dest="ref", required=True, help="Reference group value (e.g., 'White')")
    p_rr.add_argument("--threshold", dest="threshold", required=False, default="0.80", help="Flag RR < threshold (default 0.80)")
    p_rr.add_argument("--out", dest="out", required=False, help="Write RR table to CSV")
    _add_filter_args(p_rr)
    p_rr.set_defaults(func=cmd_rr)

    return p

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
