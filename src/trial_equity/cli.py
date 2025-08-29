"""
CLI for EquiEnroll pilot exports.
Usage examples:
  python -m trial_equity.cli export dap --study ABC-123 --data-cut 2025-08-25 --out out/ --from-csv data/mock_recruitment.csv
  python -m trial_equity.cli export hti1 --out out/
  python -m trial_equity.cli export audit-pack --out out/
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from .export_builder import ExportBuilder, ExportContext
from .stats import wilson_ci

def age_band(age: float | int) -> str:
    try:
        a = int(age)
    except Exception:
        return "Unknown"
    if a < 18: return "0-17"
    if a < 45: return "18-44"
    if a < 65: return "45-64"
    return "65+"

def build_dap_from_csv(csv_path: Path) -> dict:
    df = pd.read_csv(csv_path)
    required = ["race","ethnicity","sex","age","eligible","contacted","selected"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns: {missing}")

    df["age_band"] = [age_band(x) for x in df["age"]]
    # totals
    total_selected = max(1, int(df["selected"].sum()))
    # group by OMB-style tuple
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
            "goal_pct": actual_pct,   # default: proportional; adjust later if you have DAP-specific goals
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
    p_dap.add_argument("--from-csv", type=Path, required=True, help="CSV with columns race, ethnicity, sex, age, eligible, contacted, selected")

    p_card = sp2.add_parser("hti1")
    p_card.add_argument("--out", default="out")

    p_pack = sp2.add_parser("audit-pack")
    p_pack.add_argument("--out", default="out")
    p_pack.add_argument("--study", default="UNKNOWN")
    p_pack.add_argument("--data-cut", default="UNKNOWN")

    args = ap.parse_args(argv)

    if args.cmd == "export" and args.which == "dap":
        ctx = ExportContext(study_id=args.study, data_cut=args.data_cut, out_dir=args.out)
        eb = ExportBuilder(ctx)
        payload = build_dap_from_csv(args.from_csv)
        path = eb.build_dap_packet(payload)
        print(path)
    elif args.cmd == "export" and args.which == "hti1":
        ctx = ExportContext(study_id="UNKNOWN", data_cut="2025-08-29", out_dir=args.out)
        eb = ExportBuilder(ctx)
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
        path = eb.build_transparency_card(card)
        print(path)
    elif args.cmd == "export" and args.which == "audit-pack":
        ctx = ExportContext(study_id=args.study, data_cut=args.data_cut, out_dir=args.out)
        eb = ExportBuilder(ctx)
        z = eb.build_audit_pack()
        print(z)

if __name__ == "__main__":
    main()
