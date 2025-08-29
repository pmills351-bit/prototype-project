# src/trial_equity/normalize.py
from __future__ import annotations
from typing import Optional
import re

_ws = re.compile(r"\s+")

def _clean(x: Optional[str]) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.lower()
    s = s.replace(".", " ").replace("-", " ").replace("_", " ").replace("/", " ")
    s = _ws.sub(" ", s)
    return s

# Canonical labels (match tests exactly)
R_BLACK   = "Black or African American"
R_WHITE   = "White"
R_ASIAN   = "Asian"
R_AIAN    = "American Indian or Alaska Native"
R_NHPI    = "Native Hawaiian or Other Pacific Islander"
R_OTHER   = "Other"
R_UNKNOWN = "Unknown"

E_HISP    = "Hispanic or Latino"
E_NONHISP = "Not Hispanic or Latino"
E_UNKNOWN = "Unknown"

S_MALE    = "Male"
S_FEMALE  = "Female"
S_OTHER   = "Other"
S_UNKNOWN = "Unknown"

# Expanded maps with many variants
_RACE_MAP = {
    # Black / African American variants
    "black": R_BLACK,
    "african american": R_BLACK,
    "black african american": R_BLACK,
    "black or african american": R_BLACK,
    "african american or black": R_BLACK,
    "aa": R_BLACK,

    # White
    "white": R_WHITE,
    "caucasian": R_WHITE,

    # Asian
    "asian": R_ASIAN,

    # AI/AN
    "american indian or alaska native": R_AIAN,
    "american indian": R_AIAN,
    "alaska native": R_AIAN,
    "ai an": R_AIAN,
    "aian": R_AIAN,

    # NH/PI
    "native hawaiian or other pacific islander": R_NHPI,
    "native hawaiian": R_NHPI,
    "pacific islander": R_NHPI,
    "nh pi": R_NHPI,

    # Other / Unknown
    "multiracial": R_OTHER,
    "two or more races": R_OTHER,
    "two or more": R_OTHER,
    "mixed": R_OTHER,
    "other": R_OTHER,

    "unknown": R_UNKNOWN,
    "undisclosed": R_UNKNOWN,
    "not reported": R_UNKNOWN,
    "prefer not to say": R_UNKNOWN,
    "missing": R_UNKNOWN,
}

_ETH_MAP = {
    "hispanic or latino": E_HISP,
    "hispanic": E_HISP,
    "latino": E_HISP,
    "latina": E_HISP,
    "latinx": E_HISP,

    "not hispanic or latino": E_NONHISP,
    "non hispanic": E_NONHISP,
    "non hispanic or latino": E_NONHISP,
    "non-hispanic": E_NONHISP,

    "unknown": E_UNKNOWN,
    "undisclosed": E_UNKNOWN,
    "not reported": E_UNKNOWN,
    "prefer not to say": E_UNKNOWN,
    "missing": E_UNKNOWN,
}

_SEX_MAP = {
    "male": S_MALE, "m": S_MALE, "man": S_MALE,
    "female": S_FEMALE, "f": S_FEMALE, "woman": S_FEMALE,
    "nonbinary": S_OTHER, "non binary": S_OTHER, "non-binary": S_OTHER, "nb": S_OTHER, "intersex": S_OTHER, "other": S_OTHER,
    "unknown": S_UNKNOWN, "undisclosed": S_UNKNOWN, "not reported": S_UNKNOWN, "prefer not to say": S_UNKNOWN, "missing": S_UNKNOWN,
}

def normalize_race(value: Optional[str]) -> Optional[str]:
    key = _clean(value)
    if key is None:
        return None
    # direct map
    if key in _RACE_MAP:
        return _RACE_MAP[key]
    # looser heuristics
    if ("black" in key) or ("african" in key):
        return R_BLACK
    if ("white" in key) or ("caucasian" in key):
        return R_WHITE
    if "asian" in key:
        return R_ASIAN
    if ("hawaiian" in key) or ("pacific islander" in key) or ("pacific" in key):
        return R_NHPI
    if ("american indian" in key) or ("alaska native" in key) or ("aian" in key):
        return R_AIAN
    if ("unknown" in key) or ("undisclosed" in key) or ("not reported" in key):
        return R_UNKNOWN
    if ("two or more" in key) or ("multiracial" in key) or ("mixed" in key):
        return R_OTHER
    return R_OTHER

def normalize_eth(value: Optional[str]) -> Optional[str]:
    key = _clean(value)
    if key is None:
        return None
    if key in _ETH_MAP:
        return _ETH_MAP[key]
    if ("hispanic" in key) or ("latino" in key) or ("latina" in key) or ("latinx" in key):
        return E_HISP
    if ("non hispanic" in key) or ("not hispanic" in key):
        return E_NONHISP
    if ("unknown" in key) or ("undisclosed" in key) or ("not reported" in key):
        return E_UNKNOWN
    return E_NONHISP

def normalize_sex(value: Optional[str]) -> Optional[str]:
    key = _clean(value)
    if key is None:
        return None
    if key in _SEX_MAP:
        return _SEX_MAP[key]
    if key.startswith("m"):
        return S_MALE
    if key.startswith("f"):
        return S_FEMALE
    if ("unknown" in key) or ("undisclosed" in key) or ("not reported" in key):
        return S_UNKNOWN
    return S_OTHER
