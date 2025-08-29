# src/demo_artifacts.py
from datetime import datetime, timezone
import pandas as pd
import hashlib, json

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
                "url": "Binary/placeholder-id"
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
