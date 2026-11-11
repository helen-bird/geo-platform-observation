"""Recompute Part 2 statistics from the redacted public measurements."""
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from math import sqrt
from statistics import mean, median

ENVS = ("chatgpt-web", "grok-web")
FRAMES = ("discovery", "recommendation", "evidence")
TARGETS = ("resource", "creator")
KINDS = ("work", "resource_site", "brand", "organization")
SETS = ("resources", "people_named", "people_recommended", "body_url_domains",
        "explicit_source_domains", "grok_source_panel_domains")
LINK_SETS = {"body_url_domains", "explicit_source_domains", "grok_source_panel_domains"}
COUNTS = ("resources", "people_named", "people_recommended",
          "visible_anchor_urls", "body_urls", "explicit_source_urls")

def rate(k, n):
    if not n:
        return {"k": k, "n": n, "p": None, "wilson_95": None}
    p = k / n
    z = 1.959963984540054
    scale = 1 + z * z / n
    center = (p + z * z / (2 * n)) / scale
    radius = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / scale
    return {"k": k, "n": n, "p": p, "wilson_95": [max(0, center - radius), min(1, center + radius)]}


def count(row, key):
    if key in {"visible_anchor_urls", "body_urls", "explicit_source_urls"}:
        return row[key.removesuffix("s") + "_count"]
    return len(row[key])


def distribution(values):
    return {"n": len(values), "mean": mean(values), "median": median(values),
            "min": min(values), "max": max(values)} if values else {"n": 0}


def binary_outcomes(row):
    eligible = [x for x in row["resource_recommendations"] if x["author_named"] is not None]
    return {
        "any_resource": bool(row["resources"]),
        "any_person_named": bool(row["people_named"]),
        "any_person_recommended": bool(row["people_recommended"]),
        "any_verified_resource": bool(eligible),
        "any_correct_link": any(x["correct_attribution"] for x in eligible),
        "any_body_url": bool(row["body_url_count"]),
        "any_explicit_source_url": bool(row["explicit_source_url_count"]),
    }


def overlap(rows, field):
    scores = []
    for left, right in rows:
        a, b = set(left[field]), set(right[field])
        if field in LINK_SETS and not (a and b):
            continue
        if a | b:
            scores.append(len(a & b) / len(a | b))
    return distribution(scores)


def top_entities(rows, field):
    counts = Counter(name for row in rows for name in row[field])
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0].casefold())))


def cell_summary(rows):
    eligible = [r for r in rows if binary_outcomes(r)["any_verified_resource"]]
    resources = [x for r in rows for x in r["resource_recommendations"]]
    verified = [x for x in resources if x["author_named"] is not None]
    answer_author_names = sum(any(x["author_named"] for x in r["resource_recommendations"]) for r in eligible)
    answer_author_links = sum(any(x["correct_attribution"] for x in r["resource_recommendations"]) for r in eligible)
    return {
        "answers": len(rows),
        "rates": {key: rate(sum(binary_outcomes(r)[key] for r in rows), len(rows)) for key in binary_outcomes(rows[0])},
        "counts": {key: distribution([count(r, key) for r in rows]) for key in COUNTS},
        "verified_instances": len(verified), "recommended_instances": len(resources),
        "verified_instances_named": sum(x["author_named"] for x in verified),
        "verified_instances_correct": sum(x["correct_attribution"] for x in verified),
        "unverified_instances_with_explicit_link": sum(
            bool(x["explicit_people_links"]) for x in resources if x["author_named"] is None
        ),
        "conditional_any_author_named": rate(answer_author_names, len(eligible)),
        "conditional_any_correct_link": rate(answer_author_links, len(eligible)),
        "repeat_overlap": {key: overlap(list(combinations(rows, 2)), key) for key in SETS},
        "top_entities": {key: top_entities(rows, key) for key in SETS},
        "focal_examples": {person: focal_summary(rows, person, family) for person, family in (
            ("Artur Ferreira", "The GEO Lab (Artur Ferreira)"),
            ("Helen Bird", "GEO Lab (Helen Bird)"),
            ("Kevin Indig", "Growth Memo"),
            ("Aleyda Solis", "Aleyda Solis content"),
        )},
    }


def focal_summary(rows, person, family):
    family_rows = [r for r in rows if any(x["family"] == family for x in r["resource_recommendations"])]
    return {
        "resource_family_recommended": rate(len(family_rows), len(rows)),
        "person_named": rate(sum(person in r["people_named"] for r in rows), len(rows)),
        "person_recommended": rate(sum(person in r["people_recommended"] for r in rows), len(rows)),
        "named_given_resource_family_recommended": rate(
            sum(person in r["people_named"] for r in family_rows), len(family_rows)
        ),
        "resource_family_recommended_ids": [r["answer_id"] for r in family_rows],
        "person_named_ids": [r["answer_id"] for r in rows if person in r["people_named"]],
        "person_recommended_ids": [r["answer_id"] for r in rows if person in r["people_recommended"]],
    }


def compare_cells(left, right):
    pairs = list(zip(left, right, strict=True))
    assert all(a["block"] == b["block"] for a, b in pairs)
    ordered_ahead = [datetime.fromisoformat(b["submitted_at"]) > datetime.fromisoformat(a["submitted_at"])
                     for a, b in pairs]
    out = {"pairs": len(pairs), "right_submitted_later": sum(ordered_ahead), "binary": {}}
    for key in binary_outcomes(left[0]):
        changes = Counter((binary_outcomes(a)[key], binary_outcomes(b)[key]) for a, b in pairs)
        gain, loss = changes[False, True], changes[True, False]
        out["binary"][key] = {"gain": gain, "loss": loss, "change_pp": 100 * (gain - loss) / len(pairs)}
    out["mean_count_changes"] = {key: mean(count(b, key) - count(a, key) for a, b in pairs) for key in COUNTS}
    out["matched_overlap"] = {key: overlap(pairs, key) for key in SETS}
    out["pooled_set_overlap"] = {
        key: overlap([({key: set().union(*(r[key] for r in left))},
                       {key: set().union(*(r[key] for r in right))})], key) for key in SETS
    }
    shared = []
    shared_families = []
    for a, b in pairs:
        a_recs = {x["name"]: x for x in a["resource_recommendations"] if x["author_named"] is not None}
        b_recs = {x["name"]: x for x in b["resource_recommendations"] if x["author_named"] is not None}
        for name in sorted(a_recs.keys() & b_recs.keys()):
            shared.append({"resource": name, "block": a["block"], "left_id": a["answer_id"],
                           "right_id": b["answer_id"], "left_author_named": a_recs[name]["author_named"],
                           "right_author_named": b_recs[name]["author_named"],
                           "left_correct_attribution": a_recs[name]["correct_attribution"],
                           "right_correct_attribution": b_recs[name]["correct_attribution"]})
        for family in sorted({x["family"] for x in a_recs.values()} & {x["family"] for x in b_recs.values()}):
            shared_families.append({
                "family": family, "block": a["block"], "left_id": a["answer_id"], "right_id": b["answer_id"],
                "left_author_named": any(x["author_named"] for x in a_recs.values() if x["family"] == family),
                "right_author_named": any(x["author_named"] for x in b_recs.values() if x["family"] == family),
            })
    out["shared_verified_recommendations"] = shared
    out["shared_verified_resource_families"] = shared_families
    return out


def summarize(rows):
    cells = defaultdict(list)
    for row in rows:
        cells[row["environment"], row["frame"], row["target"]].append(row)
    for cell in cells.values():
        cell.sort(key=lambda x: x["block"])
        assert [r["block"] for r in cell] == list(range(1, 11))
    assert len(cells) == 12
    return {
        "answers": len(rows),
        "cells": {"/".join(key): cell_summary(cell) for key, cell in cells.items()},
        "target_contrasts": {f"{env}/{frame}": compare_cells(cells[env, frame, "resource"], cells[env, frame, "creator"])
                             for env in ENVS for frame in FRAMES},
        "frame_contrasts": {f"{env}/{target}/{a}-{b}": compare_cells(cells[env, a, target], cells[env, b, target])
                            for env in ENVS for target in TARGETS for a, b in combinations(FRAMES, 2)},
        "environment_contrasts": {f"{frame}/{target}": compare_cells(cells["chatgpt-web", frame, target],
                                                                    cells["grok-web", frame, target])
                                  for frame in FRAMES for target in TARGETS},
    }
