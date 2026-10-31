"""Why item 16 moved nothing, read after the result and deciding nothing. For each recorded piece's dark candidate: every
measured value, which fixed condition fails, and the share of its strip and branch with a dipole at or above its own. Then
what passes the whole fit on the planted tiles, and what enters each strip's top 20.

    uv run --env-file out/landers.env experiments/darkrelief_why.py

Reads out/darkrelief and out/halfcal. Output docs/reports/2026-10-31-darkrelief/why.json.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import darkrelief as dr  # noqa: E402
import halfcal as hs  # noqa: E402
import rerank as rr  # noqa: E402

from landers import relief  # noqa: E402

sites, thresholds, answers = rr.controls()
pieces = rr.tp.key_pieces(answers, thresholds, rr.tp.tuning_sources(sites))
results = rr.load(dr.OUT / "results.json")
rules = {
    b: relief.Rule(r["threshold"], r["fraction"], r["gain"], r["n"], r["passed"])
    for b, r in results["arms"]["whole_fit"]["rules"].items()
}


def load_strip(sid):
    with np.load(hs.POP / f"{sid}.npz") as z:
        s = {k: z[k] for k in ("row", "col", "score", "branch")}
    with np.load(dr.FEATURES / f"{sid}.npz") as z:
        return s, {k: z[k] for k in dr.FIELDS}


strips = {}
out = []
for p in pieces:
    sid = p["strip"]
    if sid not in strips:
        strips[sid] = load_strip(sid)
    s, f = strips[sid]
    radius = hs.match_radius_px(thresholds, rr.label_of(sid).scale_m, p["kind"])
    for i in np.flatnonzero(np.hypot(s["row"] - p["row"], s["col"] - p["col"]) <= radius):
        b = str(s["branch"][i])
        if b not in relief.BRANCHES:
            continue
        same = s["branch"] == b
        one = {k: float(f[k][i]) for k in dr.FIELDS[:5]}
        fails = []
        if not one["relief_sun_min_z"] >= relief.NOT_DARK_Z:
            fails.append("dark on the sun side")
        if not relief.HEIGHT_M[0] <= one["relief_height_m"] <= relief.HEIGHT_M[1]:
            fails.append("height")
        if not one["relief_width_m"] <= relief.MAX_WIDTH_M:
            fails.append("width")
        out.append(
            {
                "piece": f"{p['site']}/{p['piece']}/{sid}",
                "branch": b,
                **{k: round(v, 2) for k, v in one.items()},
                "fails": fails,
                "threshold": rules[b].threshold,
                "share_of_strip_branch_at_or_above": round(
                    float((f["relief_dipole"][same] >= one["relief_dipole"]).mean()), 5
                ),
            }
        )
for r in sorted(out, key=lambda x: x["piece"]):
    print(r)

# the planted tiles under the whole fit
dets, truths = hs.board_tiles(thresholds)
files = {rr.tile_key(t): t["file"][:-4] for t in hs.listed_tiles()}
keys = list(dict.fromkeys(d["tile"] for d in dets))
parts = []
for key in keys:
    with np.load(dr.TILES / f"{files[key]}.npz") as z:
        parts.append({k: z[k] for k in dr.FIELDS})
tile_f = {k: np.concatenate([x[k] for x in parts]) for k in dr.FIELDS}
pop = dr.Pop(np.array([d["branch"] for d in dets]), tile_f)
g = dr.gain_of(pop, "primary", rules)
by_tile = {}
for t in truths:
    by_tile.setdefault(t["tile"], []).append(t)


def on_truth(d):
    return any(np.hypot(d["row"] - t["row"], d["col"] - t["col"]) <= t["radius_px"] for t in by_tile.get(d["tile"], []))


passing = [d for d, v in zip(dets, g, strict=True) if v > 0]


def piece_of(d):
    return [
        f"{t['site']}/{t['piece']}"
        for t in by_tile.get(d["tile"], [])
        if np.hypot(d["row"] - t["row"], d["col"] - t["col"]) <= t["radius_px"]
    ]


def best_other(d, truth_key):
    """The best other detection of the same planted piece on the same tile, what the gain has to beat to change anything."""
    best = None
    for t in by_tile.get(d["tile"], []):
        if f"{t['site']}/{t['piece']}" != truth_key:
            continue
        for x in dets:
            if (
                x is not d
                and x["tile"] == d["tile"]
                and np.hypot(x["row"] - t["row"], x["col"] - t["col"]) <= t["radius_px"]
            ):
                if best is None or x["score"] > best["score"]:
                    best = {"branch": x["branch"], "score": round(x["score"], 3)}
    return best


passers = []
for d, v, dip in zip(dets, g, tile_f["relief_dipole"], strict=True):
    if v > 0:
        names = piece_of(d)
        passers.append(
            {
                "branch": d["branch"],
                "frozen_score": round(d["score"], 3),
                "with_gain": round(d["score"] + float(v), 3),
                "dipole": round(float(dip), 2),
                "planted_piece": names[0] if names else None,
                "best_other_detection": best_other(d, names[0]) if names else None,
            }
        )
tile = {
    "detections": len(dets),
    "dark_detections": int(sum(pop.is_[b].sum() for b in relief.BRANCHES)),
    "passing": len(passing),
    "passing_on_a_planted_piece": sum(on_truth(d) for d in passing),
    "passers": passers,
}
print(tile)

# what the whole fit brings into each strip's top 20, and how far up the passers reach
top = {}
for sid in sorted(hs.tuning_strips(sites)):
    if sid not in strips:
        strips[sid] = load_strip(sid)
    s, f = strips[sid]
    p = dr.Pop(s["branch"], f)
    gain = dr.gain_of(p, "primary", rules)
    now = s["score"] + gain
    best = np.argsort(-now, kind="stable")[:20]
    top[sid] = {"site_passing": int((gain > 0).sum()), "passing_in_top_20": int((gain[best] > 0).sum())}
    print(sid, top[sid])

dest = ROOT / "docs" / "reports" / "2026-10-31-darkrelief" / "why.json"
dest.write_text(json.dumps({"pieces": out, "planted_tiles": tile, "top_20": top}, indent=1))
print("written", dest)
