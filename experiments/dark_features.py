"""Where the recorded pieces sit among the dark-branch false alarms (detector v0.3 records features there),
and how tile_count is spread, to draft rules for the tuning loop. Reads the answer key: experiments only.

    uv run experiments/dark_features.py out/shape_v3/candidates_v03_features.json
"""

import bisect
import sys
from collections import Counter

from landers.features_eval import format_pieces, measure
from landers.score import load_json

FEATURES = (
    "two_sided",
    "shadow_height_m",
    "sun_max_z",
    "circularity",
    "fill",
    "edge_sharpness",
    "tile_rank",
    "tile_count",
)

cands = load_json(sys.argv[1])
answers = load_json("controls/tuning.json")
thresholds = load_json("controls/thresholds.json")
m = measure(cands, answers, thresholds)

print("pieces with a dark-branch candidate within the match radius")
print("(value, fraction of same-strip dark false alarms >= / <=):")
dark_only = {
    "pieces": [{**p, "candidates": [c for c in p["candidates"] if c["branch"] == "dark"]} for p in m["pieces"]]
}
print(format_pieces(dark_only, FEATURES))
print()
print("all branches, the top candidate per piece:")
top = {"pieces": [{**p, "candidates": p["candidates"][:1]} for p in m["pieces"]]}
print(format_pieces(top, ("two_sided", "shadow_height_m", "tile_rank", "tile_count", "saturated_px")))

print()
print("tile_count among bright+shadow false alarms per strip (quantiles 10/50/90) and the pieces' tile_count:")
for sid, entry in cands["strips"].items():
    vals = sorted(
        c["extra"]["tile_count"]
        for c in entry["candidates"]
        if c["branch"] in ("bright", "shadow") and "tile_count" in (c.get("extra") or {})
    )
    if not vals:
        continue
    q = [vals[int(len(vals) * f)] for f in (0.1, 0.5, 0.9)]
    tops = [c for c in entry["candidates"] if c["branch"] in ("bright", "shadow") and c["extra"].get("tile_rank") == 0]
    tc = Counter(min(c["extra"]["tile_count"] // 10 * 10, 200) for c in tops)
    print(sid, "n", len(vals), "q10/50/90", q, "| tile tops", len(tops), "by tile_count decade", sorted(tc.items()))
print()
print("recorded pieces (bright/shadow candidates): tile_rank, tile_count")
for p in m["pieces"]:
    for c in p["candidates"]:
        if c["branch"] in ("bright", "shadow"):
            f = c["features"]
            print(
                f"  {p['site']}/{p['piece']} rank {c['rank']} {c['branch']}: tile_rank {f['tile_rank']['value']:g}, "
                f"tile_count {f['tile_count']['value']:g}"
            )
            break
print()
print("dark false alarms passing two_sided >= T and shadow height in [0.5, 3], pooled, by T:")
pool = []
for sid, entry in cands["strips"].items():
    truths = []
    for site in answers["sites"]:
        for pc in site["pieces"]:
            if pc.get("strip") == sid and pc.get("line") is not None:
                truths.append((pc["line"] - 1, pc["sample"] - 1))
    for c in entry["candidates"]:
        if c["branch"] != "dark":
            continue
        e = c.get("extra") or {}
        if "two_sided" not in e:
            continue
        near = any(abs(c["row"] - r) <= 80 and abs(c["col"] - k) <= 80 for r, k in truths)
        if not near:
            pool.append((e["two_sided"], e["shadow_height_m"]))
pool.sort()
ts = [x[0] for x in pool]
for T in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
    n = sum(1 for t, h in pool if t >= T and 0.5 <= h <= 3.0)
    print(
        f"  T={T}: {n}/{len(pool)} = {n / len(pool):.5f}  (two_sided >= T alone: {len(ts) - bisect.bisect_left(ts, T)})"
    )
