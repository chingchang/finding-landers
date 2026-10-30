"""Persistence for the search: every survivor of one date looked for on every other date of the same ground.

A survivor is one of a strip's top candidates by calibrated score, as many as the adopted false-alarm bar
allows on that strip's valid area (``controls/thresholds.json`` pass.max_false_alarms_per_km2 times km2).
For a pair of strips the second date is registered to the first (``landers.persist.offset_field``), each
survivor of the first is mapped into the second and looked up in the second's whole candidate list with
``landers.persist.annotate``, the same rule as the control sites (same family within 8 px).

Three outcomes per survivor and pair: seen, not seen, or not looked at (the mapped spot falls outside the
second strip's valid ground, or no registration node is near enough). Nothing here sets a grade: the
detector's grade is kept as it is, and persistence is recorded beside it as evidence for the later stages.
"""

from __future__ import annotations

import copy
import math

from landers import persist
from landers.strip import Strip


def survivor_count(valid_area_km2: float, per_km2: float) -> int:
    return int(math.floor(valid_area_km2 * per_km2))


def survivors(entry: dict, per_km2: float) -> list[dict]:
    """The strip's top candidates by score, at most ``per_km2`` per km2 of valid ground, best first."""
    n = survivor_count(entry["valid_area_km2"], per_km2)
    ranked = sorted(entry["candidates"], key=lambda c: -float(c["score"]))
    return ranked[:n]


def in_valid(strip: Strip, row: float, col: float) -> bool:
    """Whether a full-resolution position falls on valid ground of the strip, judged on its overview."""
    ov = strip.overview.valid
    r, c = int(row // strip.overview_step), int(col // strip.overview_step)
    return 0 <= r < ov.shape[0] and 0 <= c < ov.shape[1] and bool(ov[r, c])


def look_up(
    surv_a: list[dict], cands_b: list[dict], strip_a: Strip, strip_b: Strip, nodes, radius_px: float
) -> tuple[list[dict], dict]:
    """One record per survivor of A: its rank and position in A and what was found in B. The candidates
    themselves are not changed."""
    records = []
    counts = {"seen": 0, "not_seen": 0, "off_ground": 0, "unregistered": 0}
    inside, inside_idx = [], []
    for i, c in enumerate(surv_a):
        rb, cb, _ = persist.map_to_b(strip_a, strip_b, nodes, float(c["row"]), float(c["col"]))
        if in_valid(strip_b, rb, cb):
            inside.append(copy.deepcopy(c))
            inside_idx.append(i)
        records.append({"rank": i + 1, "row": c["row"], "col": c["col"], "branch": c["branch"], "score": c["score"],
                        "seen": None, "note": "off the other strip's valid ground", "row_b": round(rb, 1),
                        "col_b": round(cb, 1)})
    persist.annotate(inside, cands_b, strip_a, strip_b, nodes, radius_px)
    for i, c in zip(inside_idx, inside):
        p = c["extra"]["persist"]
        rec = records[i]
        rec.pop("note")
        rec.update(p)
        if p.get("seen") is None:
            rec["note"] = p.get("note", "")
    for rec in records:
        if rec["seen"] is True:
            counts["seen"] += 1
        elif rec["seen"] is False:
            counts["not_seen"] += 1
        elif rec.get("note", "").startswith("off"):
            counts["off_ground"] += 1
        else:
            counts["unregistered"] += 1
    return records, counts


def combine(strip_ids: list[str], survivors_by_strip: dict, pair_results: list[dict]) -> list[dict]:
    """One row per survivor: dates looked at (its own plus every other date where it was looked up) and
    dates seen (its own plus every other date where it was seen), with the pairs listed."""
    rows = {}
    for sid in strip_ids:
        for i, c in enumerate(survivors_by_strip[sid]):
            rows[(sid, i + 1)] = {
                "strip": sid,
                "rank": i + 1,
                "row": c["row"],
                "col": c["col"],
                "branch": c["branch"],
                "score": c["score"],
                "grade": c["grade"],
                "dates_looked": 1,
                "dates_seen": 1,
                "looked_in": [],
                "seen_in": [],
                "not_seen_in": [],
            }
    for pr in pair_results:
        for d in pr["directions"].values():
            for rec in d["survivors"]:
                row = rows.get((d["from"], rec["rank"]))
                if row is None or rec["seen"] is None:
                    continue
                row["dates_looked"] += 1
                row["looked_in"].append(d["to"])
                if rec["seen"]:
                    row["dates_seen"] += 1
                    row["seen_in"].append(d["to"])
                else:
                    row["not_seen_in"].append(d["to"])
    return list(rows.values())
