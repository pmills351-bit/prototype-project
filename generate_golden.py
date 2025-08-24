# generate_golden.py
import pandas as pd, yaml
from pathlib import Path
from te_engine import apply_mapping, validate_canonical_v1_inline, normalize_race, normalize_eth, normalize_sex
# ...rest stays the same...


# Reuse mapping + validation helpers from your app
from app_streamlit import apply_mapping, validate_canonical_v1_inline

BASE = Path("data")
input_file = BASE / "input" / "sample_input.csv"
mapping_file = BASE / "mappings" / "mapping_demo.yaml"
golden_file = BASE / "golden" / "canonical_v1_golden.csv"

def main():
    # 1) Load input + mapping
    df_in = pd.read_csv(input_file)
    mapping = yaml.safe_load(mapping_file.read_text())

    # 2) Map into Canonical v1 (use a test salt)
    df_out = apply_mapping(df_in, mapping, default_site_salt="MY_SITE_SALT")

    # 3) Coerce common fields
    for col in ["eligible","selected","identified","contacted","consented","enrolled"]:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce").fillna(0).astype(int)
    if "age" in df_out.columns:
        df_out["age"] = pd.to_numeric(df_out["age"], errors="coerce")

    # 4) Validate and write
    validate_canonical_v1_inline(df_out)
    golden_file.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(golden_file, index=False)
    print(f"✅ Golden output written to {golden_file.resolve()}")

if __name__ == "__main__":
    main()
