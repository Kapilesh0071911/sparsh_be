import json


def source_stats_row(row):
    d = dict(row)
    for key in ("sebi_registered",):
        if d.get(key) is not None:
            d[key] = bool(d[key])
    d.setdefault("raw_hit_rate", None)
    d.setdefault("shrunk_hit_rate", d.get("post_mean"))
    d.setdefault("overconfidence_gap", None)

    # API Contract fields
    d["id"] = d.get("source_id")
    d["name"] = d.get("display_name")
    d["type"] = d.get("source_type")
    d["tips_total"] = d.get("n_tips") or 0
    d["tips_worked"] = d.get("n_hits") or 0

    if not d.get("evidence_level"):
        n = d["tips_total"]
        if n == 0:
            d["evidence_level"] = "none"
        elif n <= 4:
            d["evidence_level"] = "low"
        elif n <= 14:
            d["evidence_level"] = "medium"
        else:
            d["evidence_level"] = "high"

    # API Contract rule:
    # "The label is 'Too early to tell' whenever evidence_level is none or low."
    d["label"] = (
        "Too early to tell"
        if d.get("evidence_level") in ("none", "low")
        else "Track record verified"
    )

    return d
