"""Exploratory, designed after the item 13 result was seen, so it decides nothing: frozen-v1's rank and the primary
re-ranker's rank merged by taking the better of the two for each candidate (ties to the better second rank). The top
20 is then roughly the top 10 of each list, so nothing the proposer ranks in its top 10 can leave.

    uv run experiments/rerank_fusion.py --no-texture ID ID

Output out/rerank/fusion.json.
"""

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rerank as rr  # noqa: E402

from landers.rerank import model as rm  # noqa: E402


def fused(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """A score: higher is better. Both inputs are scores, higher better."""
    def rank(x):
        r = np.zeros(len(x))
        r[np.argsort(-x, kind="stable")] = np.arange(1, len(x) + 1)
        return r

    a, b = rank(first), rank(second)
    return -(np.minimum(a, b) + np.maximum(a, b) / (2.0 * len(a) + 1))


ap = argparse.ArgumentParser()
ap.add_argument("--no-texture", nargs="*", default=[])
a = ap.parse_args()
sites, thresholds, answers = rr.controls()
t = rr.build_table(sites, thresholds, answers)
tb = t["table"]
groups = rr.site_strips(sites)
targets = sorted({str(v) for v in tb.target if v})
area = float(rr.load(rr.RUN / "run.json")["area_km2"])
median_km2 = statistics.median(rr.target_areas(targets).values())
rate_list = [(f"N{n}", n / median_km2) for n in rr.TOP_NS] + [("board_rate", float(thresholds["pass"]["max_false_alarms_per_km2"]))]
no_texture = set(a.no_texture)
frozen = rr.key_ranks({sid: e["rows"] for sid, e in t["lists"].items()}, answers, thresholds)
ranks: dict = {}
found: dict = {name: [] for name, _ in rate_list}
det_rows = np.array([d["row_index"] for d in t["detections"]], int)
for site, strips in groups.items():
    f = rr.fold(tb, t, site, strips, targets, "primary", answers, thresholds, rate_list, area, no_texture)
    lists = {}
    for sid in strips:
        if sid in t["lists"]:
            e = t["lists"][sid]
            s = fused(tb.score[e["idx"]], f["scores_off"][e["idx"]])
            lists[sid] = [{**x, "score": float(v)} for x, v in zip(e["rows"], s, strict=True)]
    ranks.update(rr.key_ranks(lists, {**answers, "sites": [s for s in answers["sites"] if s["name"] == site]}, thresholds))
    s_det = fused(tb.score[det_rows], f["scores_on"][det_rows])
    dets = [{**d, "score": float(v)} for d, v in zip(t["detections"], s_det, strict=True)]
    for name, fa in rate_list:
        found[name] += [x for x in rr.transplant_rows(dets, t["truths"], area, fa, no_texture) if x["site"] == site]
    print(site, flush=True)
dropped = sorted(k for k, v in frozen.items() if v is not None and v <= 20 and not (ranks.get(k) is not None and ranks[k] <= 20))
out = {"what": __doc__.split("\n\n")[0], "key_curve": rr.curve(ranks.values()), "key_n": len(ranks), "key_interval_95_at_20": rm.wilson(rr.curve(ranks.values())["20"], len(ranks)),
       "dropped_from_top_20": dropped, "key_ranks": ranks, "transplant": {k: rr.summarise(v) for k, v in found.items()}}
rr.write_json(rr.OUT / "fusion.json", out)
print(out["key_curve"], dropped, {k: (v["found"], v["n"]) for k, v in out["transplant"].items()}, out["transplant"]["N20"]["by_ground"])
