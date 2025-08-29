"""
CLI for EquiEnroll pilot exports (with column mapping + signatures).
Usage examples:
  python -m trial_equity.cli export dap --study ABC-123 --data-cut 2025-08-28 --out out/ --from-csv data/mock.csv --loose
  python -m trial_equity.cli export dap --study ABC-123 --data-cut 2025-08-28 --out out/ --from-csv data/mock.csv --map contacted=screened,sex=gender
  python -m trial_equity.cli export hti1 --out out/
  python -m trial_equity.cli export audit-pack --out out/ --study ABC-123 --data-cut 2025-08-28
  python -m trial_equity.cli export signatures --out out/ --study ABC-123 --data-cut 2025-08-28 --from-json example_signers.json
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd
from .export_builder import ExportBuilder, ExportContext
from .stats import wilson_ci

REQUIRED = ["race","ethnicity","sex","age","eligible","contacted","selected"]

SYNONYMS = {
    "race": ["race","Race","RACE","omb_race","race_category","race_code"],
    "ethnicity": ["ethnicity","Ethnicity","ETHNICITY","hispanic","hispanic_indicator","ethnic_group","ethnicity_code"],
    "sex": ["sex","Sex","SEX","gender","Gender","GENDER"],
    "age": ["age","Age","AGE","age_years","AgeYears","years","AGE_YRS"],
    "eligible": ["eligible","Eligible","ELIGIBLE","is_eligible","pre_screen_eligible","meets_eligibility","elig_flag"],
    "contacted": ["contacted","Contacted","CONTACTED","screened","pre_screened","contact_attempted","outreach_contacted"],
    "selected": ["selected","Selected","SELECTED","enrolled","randomized","included","chosen"]
}

def _find_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    # exact match first
    for n in names:
        if n in df.columns:
            return n
    # case-insensitive
    lower = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None

def _binarize(val):
    if pd.isna(val): return 0
    if isinstance(val, (int, float)):
        try:
            return 1 if int(val) > 0 else 0
        except Exception:
            return 0
    s = str(val).strip().lower()
    if s in ("1","y","yes","true","t"): return 1
    return 0

def _normalize_ethnicity(val):
    if pd.isna(val): return "Unknown"
    s = str(val).strip().lower()
    if s in ("1","y","yes","true","t","hispanic","hispanic or latino","latino","latinx"):
        return "Hispanic"
    if s in ("0","n","no","false","f","non-hispanic","not hispanic or latino","nonhispanic"):
        return "Non-Hispanic"
    if "hispanic" in s:
        return "Hispanic" if "non" not in s else "Non-Hispanic"
    return val if val else "Unknown"

def _normalize_sex(val):
    if pd.isna(val): return "Unknown"
    s = str(val).strip().lower()
    if s in ("m","male"): return "M"
    if s in ("f","female"): return "F"
    return val

def _coerce_numeric(val):
    try:
        return float(val)
    except Exception:
        return None

def normalize_df(df: pd.DataFrame, mapping: Optional[Dict[str,str]] = None, loose: bool = False) -> pd.DataFrame:
    out = pd.DataFrame()
    for req in REQUIRED:
        src = None
        if mapping and mapping.get(req) in df.columns:
            src = mapping[req]
        elif loose:
            src = _find_col(df, SYNONYMS[req])

        if src is None and req in df.columns:
            src = req

        if src is None:
            if req in ("eligible","contacted","selected"):
                out[req] = 0
            elif req in ("race","ethnicity","sex"):
                out[req] = "Unknown"
            elif req == "age":
                out[req] = None
            continue

        series = df[src]
        if req in ("eligible","contacted","selected"):
            out[req] = series.map(_binarize)
        elif req == "ethnicity":
            out[req] = series.map(_normalize_ethnicity)
        elif req == "sex":
            out[req] = series.map(_normalize_sex)
        elif req == "age":
            out[req] = series.map(_coerce_numeric)
        else:
            out[req] = series.astype(str)

    return out

def _parse_map(map_str: Optional[str]) -> Dict[str,str]:
    m: Dict[str,str] = {}
    if not map_str:
        return m
    pairs = [p.strip() for p in map_str.split(",") if p.strip()]
    for p in pairs:
        if "=" in p:
            k, v = p.split("=",1)
            k = k.strip(); v = v.strip()
            if k in REQUIRED:
                m[k] = v
    return m

def age_band(age: float | int) -> str:
    try:
        a = int(age)
    except Exception:
        return "Unknown"
    if a < 18: return "0-17"
    if a < 45: return "18-44"
    if a < 65: return "45-64"
    return "65+"

def build_dap_from_csv(csv_path: Path, mapping: Optional[Dict[str,str]] = None, loose: bool = False) -> dict:
    df_raw = pd.read_csv(csv_path)
    df = normalize_df(df_raw, mapping=mapping, loose=loose)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns after normalization: {missing}. Use --loose and/or --map a=b,c=d")

    df["age_band"] = [age_band(x) for x in df["age"]]
    total_selected = max(1, int(df["selected"].sum()))

    groups = []
    for keys, g in df.groupby(["race","ethnicity","sex","age_band"], dropna=False):
        race, eth, sex, band = keys
        eligible_n = int(g["eligible"].sum())
        contacted_n = int(g["contacted"].sum())
        selected_n = int(g["selected"].sum())
        contact_rate = contacted_n / max(1, eligible_n)
        cl, cu = wilson_ci(contacted_n, max(1, eligible_n))
        actual_pct = selected_n / total_selected
        groups.append({
            "group": {"race": str(race), "ethnicity": str(eth), "sex": str(sex), "age_band": str(band)},
            "goal_pct": actual_pct,
            "actual_pct": actual_pct,
            "contact_rate": contact_rate,
            "contact_ci": {"lower": cl, "upper": cu, "method": "wilson"}
        })
    payload = {
        "schema_version":"dap.v1",
        "subgroups": groups,
        "milestones": [],
        "signatures": []
    }
    return payload

def main(argv=None):
    ap = argparse.ArgumentParser(prog="equienroll")
    sp = ap.add_subparsers(dest="cmd", required=True)

    exp = sp.add_parser("export", help="Build exports")
    sp2 = exp.add_subparsers(dest="which", required=True)

    p_dap = sp2.add_parser("dap")
    p_dap.add_argument("--study", required=True)
    p_dap.add_argument("--data-cut", required=True)
    p_dap.add_argument("--out", default="out")
    p_dap.add_argument("--from-csv", type=Path, required=True, help="CSV with enrollment columns (loose mapping supported)")
    p_dap.add_argument("--loose", action="store_true", help="Attempt auto-mapping of common column synonyms")
    p_dap.add_argument("--map", type=str, help="Comma-separated pairs mapping required columns, e.g., contacted=screened,sex=gender")

    p_card = sp2.add_parser("hti1")
    p_card.add_argument("--out", default="out")

    p_pack = sp2.add_parser("audit-pack")
    p_pack.add_argument("--out", default="out")
    p_pack.add_argument("--study", default="UNKNOWN")
    p_pack.add_argument("--data-cut", default="UNKNOWN")

    # NEW: signatures subcommand
    p_sig = sp2.add_parser("signatures")
    p_sig.add_argument("--out", default="out")
    p_sig.add_argument("--study", required=True)
    p_sig.add_argument("--data-cut", required=True)
    p_sig.add_argument("--from-json", type=Path, required=True)

    args = ap.parse_args(argv)

    if args.cmd == "export" and args.which == "dap":
        ctx = ExportContext(study_id=args.study, data_cut=args.data_cut, out_dir=args.out)
        eb = ExportBuilder(ctx)
        mapping = _parse_map(args.map)
        payload = build_dap_from_csv(args.from_csv, mapping=mapping, loose=args.loose)
        path = eb.build_dap_packet(payload)
        print(path)

    elif args.cmd == "export" and args.which == "hti1":
        ctx = ExportContext(study_id="UNKNOWN", data_cut="2025-08-28", out_dir=args.out)
        eb = ExportBuilder(ctx)
        card = {
            "artifact_id":"EquiEnroll-TransparencyCard",
            "intended_use":"Recruitment fairness analytics for clinical trials",
            "inputs":["race","ethnicity","sex","age","eligible","contacted","selected"],
            "logic_summary":"Parity gaps + Wilson CIs; action queues for under-reached groups",
            "performance":[],
            "limitations":["Small-n instability in rare subgroups"],
            "irm":{"risks":["missing race"],"mitigations":["guardrails"],"monitoring":"quarterly fairness check"},
            "version": ExportContext(study_id='x', data_cut='x', out_dir='x').version
        }
        path = eb.build_transparency_card(card)
        print(path)

    elif args.cmd == "export" and args.which == "audit-pack":
        ctx = ExportContext(study_id=args.study, data_cut=args.data_cut, out_dir=args.out)
        eb = ExportBuilder(ctx)
        z = eb.build_audit_pack()
        print(z)

    elif args.cmd == "export" and args.which == "signatures":
        ctx = ExportContext(study_id=args.study, data_cut=args.data_cut, out_dir=args.out)
        eb = ExportBuilder(ctx)
        with open(args.from_json, encoding="utf-8") as f:
            signers = json.load(f)["signers"]
        p = eb.build_signature_manifest(signers)
        print(p)

if __name__ == "__main__":
    main()