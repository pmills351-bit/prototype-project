def _clean(x):
    if x is None:
        return ""
    return str(x).strip().lower()

def normalize_race(value: str) -> str:
    v = _clean(value)
    if v in ("", "unknown", "unk"):
        return "Unknown"
    if v in ("declined", "refused"):
        return "Declined"
    opts = {
        "white": "White",
        "black": "Black or African American",
        "african american": "Black or African American",
        "aa": "Black or African American",
        "asian": "Asian",
        "american indian": "American Indian or Alaska Native",
        "alaska native": "American Indian or Alaska Native",
        "native hawaiian": "Native Hawaiian or Other Pacific Islander",
        "pacific islander": "Native Hawaiian or Other Pacific Islander",
        "two or more": "Multiple",
        "multiracial": "Multiple",
        "multiple": "Multiple",
    }
    for k, out in opts.items():
        if k in v:
            return out
    return "Unknown"

def normalize_eth(value: str) -> str:
    v = _clean(value)
    if v in ("", "unknown", "unk"):
        return "Unknown"
    if v in ("declined", "refused"):
        return "Declined"
    NEG = {
        "not hispanic","non-hispanic","not latino","non latino",
        "not hispanic or latino","not of hispanic origin",
    }
    if any(n in v for n in NEG):
        return "Not Hispanic or Latino"
    if "hispanic" in v or "latino" in v:
        return "Hispanic or Latino"
    return "Unknown"

def normalize_sex(value: str) -> str:
    v = _clean(value)
    if v in ("", "unknown", "unk"):
        return "Unknown"
    if v in ("declined", "refused"):
        return "Declined"
    if v in ("female", "f"):
        return "Female"
    if v in ("male", "m"):
        return "Male"
    if "intersex" in v:
        return "Intersex"
    return "Unknown"
