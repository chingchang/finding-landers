"""Scratch: where a rule threshold could sit. For each branch and recorded feature, the pooled false-alarm
quantiles on the tuning strips (so a threshold with pass fraction 0.05 or 0.01 can be read off) beside the
value of every recorded piece's candidate, from an unruled candidates file and the key.

    uv run experiments/feature_quantiles.py out/shape_v1/candidates_v02b_features.json

Also prints the same for the injection run's detections split into hits and false alarms, if given:

    uv run experiments/feature_quantiles.py out/shape_v1/candidates_v02b_features.json \\
        out/transplant_t2/transplant_t2.json
"""

import math
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, ".")
from landers.features_eval import _numeric_features  # noqa: E402
from landers.score import load_json, match_radius_px  # noqa: E402
from landers.tune import injection_truths  # noqa: E402

QS = (0.90, 0.95, 0.99, 0.999)


def main():
    key = load_json(sys.argv[1])
    answers = load_json("controls/tuning.json")
    thr = load_json("controls/thresholds.json")
    truth = defaultdict(list)
    for s in answers["sites"]:
        for p in s["pieces"]:
            if p.get("line") is not None:
                truth[p["strip"]].append((s["name"], p["piece"], p["line"] - 1, p["sample"] - 1))
    fa = defaultdict(lambda: defaultdict(list))
    hits = []
    for sid, e in key["strips"].items():
        r = match_radius_px(thr, e["scale_m"])
        ranked = sorted(e["candidates"], key=lambda c: -c["score"])
        for i, c in enumerate(ranked, 1):
            f = _numeric_features(c.get("extra"))
            if not f:
                continue
            near = [(a, b) for a, b, rr, cc in truth.get(sid, []) if math.hypot(c["row"] - rr, c["col"] - cc) <= r]
            if near:
                hits.append((near[0], c["branch"], i, f))
            else:
                for k, v in f.items():
                    fa[c["branch"]][k].append(v)
    for br in sorted(fa):
        print(f"\n== {br}: false-alarm quantiles (pooled over the tuning strips) and piece values ==")
        for k in sorted(fa[br]):
            v = np.array(fa[br][k])
            qs = " ".join(f"q{q:.3f}={np.quantile(v, q):.3g}" for q in QS)
            lo = " ".join(f"q{1 - q:.3f}={np.quantile(v, 1 - q):.3g}" for q in QS)
            pieces = "  ".join(f"{a[0]}/{a[1]}@{i}={f.get(k)}" for a, b, i, f in hits if b == br and k in f)
            print(f"{k:16s} n={len(v):6d}  high: {qs}\n{'':16s}          low:  {lo}\n{'':16s}  pieces: {pieces}")
    if len(sys.argv) > 2:
        run = load_json(sys.argv[2])
        truths = injection_truths(run, thr)
        by_tile = defaultdict(list)
        for t in truths:
            by_tile[t["tile"]].append(t)
        ifa = defaultdict(lambda: defaultdict(list))
        ihit = defaultdict(lambda: defaultdict(list))
        for d in run["detections"]:
            f = _numeric_features(d.get("features"))
            if not f:
                continue
            m = [
                t
                for t in by_tile.get(d["tile"], [])
                if math.hypot(d["row"] - t["row"], d["col"] - t["col"]) <= t["radius_px"]
            ]
            dst = ihit[d["branch"]] if m else ifa[d["branch"]]
            for k, v in f.items():
                dst[k].append(v)
        for br in sorted(ifa):
            print(f"\n== injection {br}: false-alarm quantiles and hit quantiles ==")
            for k in sorted(ifa[br]):
                v = np.array(ifa[br][k])
                h = np.array(ihit[br].get(k, []))
                qs = " ".join(f"q{q:.3f}={np.quantile(v, q):.3g}" for q in QS)
                hq = (
                    " ".join(f"q{q:.2f}={np.quantile(h, q):.3g}" for q in (0.1, 0.25, 0.5, 0.75, 0.9))
                    if len(h)
                    else "-"
                )
                print(f"{k:16s} false n={len(v):6d} {qs}\n{'':16s} hits  n={len(h):6d} {hq}")


if __name__ == "__main__":
    main()
