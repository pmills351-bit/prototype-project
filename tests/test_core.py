# tests/test_core.py
import math
import pandas as pd
import pytest
import trial_equity.metrics as M

def _canon(**row):
    base = dict(
        site_id="SITE_X", trial_id="NCT00000000", patient_id="p",
        race="White", ethnicity="Not Hispanic or Latino", sex="Female", age=50,
        eligible=0, selected=0, identified=0, contacted=0, consented=0, enrolled=0,
        identified_at=None, contacted_at=None, match_score=None, matched_criteria="{}",
        source_system="unit", schema_version="1.0.0", ingested_at=None, load_batch_id="test",
    )
    base.update(row)
    return base

def approx(x, eps=1e-9):
    class _A:
        def __eq__(self, other):
            try:
                return abs(float(other) - float(x)) <= eps
            except Exception:
                return False
    return _A()

def _call_group_rate_ci(df, group="race", num="contacted", denom_mask=None):
    """
    Call group_rate_ci using several possible signatures:
      1) df, group_col, numerator_col, den_cond_col="eligible"
      2) df, group_col=?, numerator_col=?, denom_filter = mask
      3) positional fallback: (df, "race", "contacted", "eligible")
      4) kw fallback: group="race", numerator="contacted", denominator="eligible"
    """
    # 1) your current API (den_cond_col expects a column name)
    try:
        return M.group_rate_ci(df=df, group_col=group, numerator_col=num, den_cond_col="eligible")
    except TypeError:
        pass

    # 2) mask-style API
    if denom_mask is not None:
        try:
            return M.group_rate_ci(df=df, group_col=group, numerator_col=num, denom_filter=denom_mask)
        except TypeError:
            pass

    # 3) positional fallback
    try:
        return M.group_rate_ci(df, group, num, "eligible")
    except TypeError:
        pass

    # 4) generic kw fallback
    try:
        return M.group_rate_ci(df=df, group=group, numerator=num, denominator="eligible")
    except TypeError as e:
        raise AssertionError(f"Could not call group_rate_ci with known signatures: {e}")

def _pick_col(df, *cands):
    for c in cands:
        if c in df.columns: return c
    raise AssertionError(f"Expected one of {cands}, got {list(df.columns)}")

def test_group_rate_ci_selection_contacted_given_eligible():
    rows = [
        _canon(race="A", eligible=1, contacted=1),
        _canon(race="A", eligible=1, contacted=1),
        _canon(race="A", eligible=1, contacted=0),
        _canon(race="B", eligible=1, contacted=1),
        _canon(race="B", eligible=1, contacted=0),
        _canon(race="B", eligible=1, contacted=0),
    ]
    df = pd.DataFrame(rows)
    out = _call_group_rate_ci(df, group="race", num="contacted", denom_mask=df["eligible"] == 1)

    c_group = _pick_col(out, "race", "group")
    c_den   = _pick_col(out, "n_denom", "denom", "n_den")
    c_num   = _pick_col(out, "n_num", "num", "n_numr")
    c_rate  = _pick_col(out, "rate", "p", "prop")

    a = out.loc[out[c_group] == "A"].iloc[0]
    b = out.loc[out[c_group] == "B"].iloc[0]

    assert a[c_den] == 3 and a[c_num] == 2 and a[c_rate] == approx(2/3)
    assert b[c_den] == 3 and b[c_num] == 1 and b[c_rate] == approx(1/3)

    for ci in ("ci_low", "ci_high"):
        assert ci in out.columns
    for r in (a, b):
        for ci in ("ci_low", "ci_high"):
            v = float(r[ci]); assert 0.0 <= v <= 1.0

def test_rr_path_handles_zero_denoms():
    # Ref group: 2/4 = 0.5; Test group: zero denominators → undefined RR
    ref = [_canon(race="Ref", eligible=1, contacted=x) for x in (1, 1, 0, 0)]
    tst = [_canon(race="Test", eligible=0, contacted=0), _canon(race="Test", eligible=0, contacted=0)]
    df = pd.DataFrame(ref + tst)

    rates = _call_group_rate_ci(df, group="race", num="contacted", denom_mask=df["eligible"] == 1)

    if hasattr(M, "risk_ratio_ci"):
        rr_df = M.risk_ratio_ci(rates_df=rates, group_col="race", ref_value="Ref")
    elif hasattr(M, "rr_table"):
        rr_df = M.rr_table(rates_df=rates, group_col="race", ref_value="Ref", threshold=0.80)
    else:
        pytest.skip("No RR function exposed in trial_equity.metrics")

    c_group = _pick_col(rr_df, "race", "group")
    c_rr    = _pick_col(rr_df, "rr", "risk_ratio")

    r = rr_df.loc[rr_df[c_group] == "Ref"].iloc[0]
    assert abs(float(r[c_rr]) - 1.0) < 1e-9

    t = rr_df.loc[rr_df[c_group] == "Test"].iloc[0]
    val = t.get(c_rr, float("nan"))
    assert str(val) in ("nan", "NaN", "None", "—") or (isinstance(val, float) and math.isnan(val))
