# -*- coding: utf-8 -*-

from trial_equity import mapping_runtime as mr


def test_env_exposes_required_helpers_and_salt():
    env = mr._build_eval_env("TEST_SALT")
    # required keys are present
    for key in ("SALT", "parse_dt", "hash_id"):
        assert key in env, f"missing {key} in eval env"

    # smoke: helpers callable and SALT wired
    assert callable(env["parse_dt"])
    assert callable(env["hash_id"])
    assert env["SALT"] == "TEST_SALT"
