"""How many bright components the injection tiles hold (tile_count, detector v0.3), and the tile_rank and
tile_count of the bright detection on each planting tile_top lifted. Reads a transplant run only.

    uv run experiments/injection_tile_count.py out/transplant_t4/transplant_t4.json
"""

import math
import sys

from landers.score import load_json

t = load_json(sys.argv[1])
bright = [d for d in t["detections"] if d["branch"] in ("bright", "shadow")]
tc = sorted(d["features"]["tile_count"] for d in bright)
n = len(tc)
print(
    "bright+shadow detections", n, "tile_count q10/50/90", tc[int(n * 0.1)], tc[n // 2], tc[int(n * 0.9)], "min", tc[0]
)
per_tile = {d["tile"]: d["features"]["tile_count"] for d in bright}
v = sorted(per_tile.values())
print(
    "tiles with a bright detection",
    len(per_tile),
    "of",
    t["n_tiles"],
    "| bright components per tile: min/median/max",
    v[0],
    v[len(v) // 2],
    v[-1],
    "| tiles under 10:",
    sum(1 for x in v if x < 10),
)
print()
print("plantings (hardware, not sham): best bright/shadow detection within the match radius")
for p in t["placements"]:
    if p.get("sham") or p["kind"] != "hardware":
        continue
    best = None
    for d in bright:
        if d["tile"] != p["tile"]:
            continue
        if math.hypot(d["row"] - p["row"], d["col"] - p["col"]) <= p["match_radius_px"]:
            if best is None or d["score"] > best["score"]:
                best = d
    if best:
        f = best["features"]
        where = f"tile_rank {f['tile_rank']}, tile_count {f['tile_count']}"
        print(f"  {p['site']}/{p['piece']}: score {best['score']}, {where}")
