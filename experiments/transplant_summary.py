"""Print the tables of a transplant run (out/transplant_<run>/transplant_<run>.json) for a report.

uv run experiments/transplant_summary.py out/transplant_t1/transplant_t1.json
"""

import json
import statistics as st
import sys
from collections import Counter, defaultdict

r = json.load(open(sys.argv[1]))
thr = r["score"]["score_threshold"]
print("run", r["run"], "seconds", r["seconds"], "tiles", r["n_tiles"], "area_km2", r["area_km2"], "threshold", thr)
print("detector calibration", r["detector"]["calibration"], "min score", r["detector"]["min_calibrated_score"])
print("skipped", r["skipped"])
print("copies", r["copies"], "nearest", r["nearest"], "tiles_per_strip", r["tiles_per_strip"], "seed", r["seed"])
print()
print("targets of each source")
for k, v in r["targets_of"].items():
    print(" ", k, v)
print("targets: id incidence tan azimuth scale tiles")
for k, v in r["targets"].items():
    print(" ", k, v["incidence_deg"], v["tan_incidence"], v["sub_solar_azimuth_deg"], v["scale_m"], len(v["tiles"]))
print("sources: id incidence tan azimuth scale")
for k, v in r["sources"].items():
    print(" ", k, v["incidence_deg"], v["tan_incidence"], v["sub_solar_azimuth_deg"], v["scale_m"])
print()
print("cuts: site piece kind radius_px half_px background_dn saturated nodata other_pieces")
for c in r["cuts"]:
    if not c["sham"]:
        print(
            " ",
            c["site"],
            c["piece"],
            c["kind"],
            c["radius_px"],
            c["half_px"],
            round(c["background_dn"]),
            c["n_saturated"],
            c["n_nodata"],
            c["other_pieces_in_cut"],
        )
print("sham cuts: site piece background_dn saturated")
for c in r["cuts"]:
    if c["sham"]:
        print(" ", c["site"], c["piece"], round(c["background_dn"]), c["n_saturated"])
print()
per = defaultdict(list)
for p in r["placements"]:
    per[(p["sham"], p["site"], p["piece"])].append(p)
print("per piece: sham site piece | n found any_detection median_best_score ranks_in_tile branches")
for k in sorted(per):
    ps = per[k]
    best = [p["best"] for p in ps if p["best"]]
    print(
        " ",
        k,
        len(ps),
        sum(p["found_at_threshold"] for p in ps),
        len(best),
        round(st.median([b["score"] for b in best]), 2) if best else None,
        sorted(b["rank_in_tile"] for b in best),
        dict(Counter(b["branch"] for b in best)),
    )
print()
tg = defaultdict(lambda: [0, 0, 0])
for p in r["placements"]:
    if p["sham"]:
        continue
    t = tg[p["target"]]
    t[0] += 1
    t[1] += p["found_at_threshold"]
    t[2] += p["best"] is not None
dets = Counter(d["tile"].split(":")[0] for d in r["detections"])
kept = Counter(d["tile"].split(":")[0] for d in r["detections"] if thr is None or d["score"] > thr)
print("per target: id | real placements, found, with any detection | detections, kept above threshold")
for k in sorted(tg):
    print(" ", k, tg[k], dets[k], kept[k])
print()
print("tan ratio by source site", sorted({(p["site"], p["tan_ratio"]) for p in r["placements"]}))
print(
    "rotation by source site and target", sorted({(p["site"], p["target"], p["rotation_deg"]) for p in r["placements"]})
)
print(
    "sham hits",
    [(p["site"], p["piece"], p["target"], p["best"]) for p in r["placements"] if p["sham"] and p["found_at_threshold"]],
)
print(
    "sham with any detection", sum(1 for p in r["placements"] if p["sham"] and p["best"]), "of", r["n_sham_placements"]
)
print("kept by branch", dict(Counter(d["branch"] for d in r["detections"] if thr is None or d["score"] > thr)))
print("score by kind rows", r["score_by_kind"]["rows"])
print("score by site rows")
for row in r["score_by_site"]["rows"]:
    print(" ", row)
