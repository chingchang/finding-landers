"""Where the t5 (per-strip) injection run's kept detections, false alarms and sham hits sit, by target strip."""

import json
import math
import sys

t5 = json.load(open(sys.argv[1]))
t4 = json.load(open(sys.argv[2]))
same_tiles = all(
    sorted(map(tuple, t5["targets"][k]["tiles"])) == sorted(map(tuple, t4["targets"][k]["tiles"]))
    for k in t5["targets"]
)
print("same planted tiles as t4:", same_tiles)
thr = t5["score"]["score_threshold"]
print("threshold", thr)
truths = [p for p in t5["placements"] if not p.get("sham")]
by_tile = {}
for d in t5["detections"]:
    by_tile.setdefault(d["tile"], []).append(d)


def strip_of(tile):
    return tile.split(":")[0] if ":" in tile else tile.rsplit("_", 1)[0]


print("tile key example:", t5["detections"][0]["tile"])
rows = {}
for d in t5["detections"]:
    s = strip_of(d["tile"])
    r = rows.setdefault(s, {"dets": 0, "kept": 0, "branches": {}})
    r["dets"] += 1
    if thr is None or float(d["score"]) > thr:
        r["kept"] += 1
        r["branches"][d["branch"]] = r["branches"].get(d["branch"], 0) + 1
for s, r in sorted(rows.items()):
    print(f"{s}: detections {r['dets']}, kept {r['kept']}, kept by branch {r['branches']}")
# score distribution of kept detections
kept = sorted((float(d["score"]) for d in t5["detections"] if thr is None or float(d["score"]) > thr), reverse=True)
print("kept scores:", [round(x, 3) for x in kept])
# sham hits
for p in t5["placements"]:
    if not p.get("sham"):
        continue
    r = float(p["match_radius_px"])
    hits = [
        d
        for d in by_tile.get(p["tile"], [])
        if (thr is None or float(d["score"]) > thr)
        and math.hypot(float(d["row"]) - p["row"], float(d["col"]) - p["col"]) <= r
    ]
    if hits:
        print(
            "sham hit",
            p["site"],
            p["piece"],
            p["tile"],
            [(h["branch"], h["score"], h["features"].get("raw_score")) for h in hits],
        )
# per-strip curves used: which strips have no curve for a branch
sc = json.load(open(sys.argv[3]))
for sid, c in sc["strips"].items():
    print(
        sid,
        {b: (v["n"], round(v["scores"][0], 2) if v["scores"] else None) for b, v in c["branches"].items()},
        "floor",
        c["floor_log_rate"],
    )
