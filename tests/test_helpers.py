# -*- coding: utf-8 -*-

import pandas as pd

from trial_equity.mapping_runtime import parse_dt, hash_id


def test_parse_dt_basic_and_invalid():
    # valid ISO
    t = parse_dt("2025-08-10T09:15:00Z")
    assert isinstance(t, pd.Timestamp)
    assert t.tzinfo is not None  # coerced to UTC
    # invalid -> NaT
    assert pd.isna(parse_dt("not-a-date"))
    # None -> NaT
    assert pd.isna(parse_dt(None))


def test_hash_id_stability_and_salt_variation():
    a1 = hash_id("P001", "SALT_A")
    a2 = hash_id("P001", "SALT_A")
    b1 = hash_id("P001", "SALT_B")

    # stable for same inputs
    assert a1 == a2
    # changes with salt
    assert a1 != b1
    # length 12 hex
    assert len(a1) == 12 and all(c in "0123456789abcdef" for c in a1)
