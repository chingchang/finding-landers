"""Item 14's inputs, no model call: the combined list and the transplant vote set, both from item 13's primary folds.

    uv run experiments/deep14_inputs.py --no-texture ID ID --transplant-top 40

Every candidate of a strip's exported list takes the better of its frozen-v1 rank and its leave-one-site-out re-ranker
rank (the fusion of experiments/rerank_fusion.py, chosen after seeing item 13's result; Decisions of 10-30 15:45). The
key and transplant curves are recomputed and must equal out/rerank/fusion.json, or nothing is written.

Writes under out/deep14/inputs/:
- candidates_combined.json: per strip, the rows in combined order, each with its export rank and both source ranks.
- transplant_folds.npz and transplant_detections.json: each fold's combined score for every detection.
- transplant_votes.json: the detections to vote on, the union of each fold's top --transplant-top.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rerank as rr  # noqa: E402

OUT = rr.config.REPO_ROOT / "out" / "deep14" / "inputs"


def rank_of(x: np.ndarray) -> np.ndarray:
    r = np.zeros(len(x), int)
    r[np.argsort(-x, kind="stable")] = np.arange(1, len(x) + 1)
    return r


def fused(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """As experiments/rerank_fusion.py: the better rank decides, the other breaks ties. Higher is better."""
    return -(np.minimum(a, b) + np.maximum(a, b) / (2.0 * len(a) + 1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-texture", nargs="*", default=[])
    ap.add_argument("--transplant-top", type=int, default=40)
    a = ap.parse_args()
    sites, thresholds, answers = rr.controls()
    t = rr.build_table(sites, thresholds, answers)
    tb = t["table"]
    targets = sorted({str(v) for v in tb.target if v})
    area = float(rr.load(rr.RUN / "run.json")["area_km2"])
    median_km2 = statistics.median(rr.target_areas(targets).values())
    rate_list = [(f"N{n}", n / median_km2) for n in rr.TOP_NS] + [("board_rate", float(thresholds["pass"]["max_false_alarms_per_km2"]))]
    no_texture = set(a.no_texture)
    det_rows = np.array([d["row_index"] for d in t["detections"]], int)

    strips: dict = {}
    ranks: dict = {}
    fold_scores: dict = {}
    found: dict = {name: [] for name, _ in rate_list}
    for site, sids in rr.site_strips(sites).items():
        f = rr.fold(tb, t, site, sids, targets, "primary", answers, thresholds, rate_list, area, no_texture)
        lists = {}
        for sid in sids:
            if sid not in t["lists"]:
                continue
            e = t["lists"][sid]
            frozen, rerank = rank_of(tb.score[e["idx"]]), rank_of(f["scores_off"][e["idx"]])
            s = fused(frozen, rerank)
            rows = [{**x, "score": float(v), "export_rank": int(x["rank"]), "frozen_rank": int(fr), "rerank_rank": int(rr_)}
                    for x, v, fr, rr_ in zip(e["rows"], s, frozen, rerank, strict=True)]
            lists[sid] = rows
            strips[sid] = {"site": site, "scale_m": rr.label_of(sid).scale_m, "candidates": sorted(rows, key=lambda c: -c["score"])}
        ranks.update(rr.key_ranks(lists, {**answers, "sites": [s for s in answers["sites"] if s["name"] == site]}, thresholds))
        s_det = fused(rank_of(tb.score[det_rows]), rank_of(f["scores_on"][det_rows]))
        fold_scores[site] = s_det.astype(np.float64)
        dets = [{**d, "score": float(v)} for d, v in zip(t["detections"], s_det, strict=True)]
        for name, fa in rate_list:
            found[name] += [x for x in rr.transplant_rows(dets, t["truths"], area, fa, no_texture) if x["site"] == site]
        print(site, flush=True)

    key_curve = rr.curve(ranks.values())
    tp_curve = {k: rr.summarise(v)["found"] for k, v in found.items()}
    want = rr.load(rr.OUT / "fusion.json")
    if key_curve != want["key_curve"] or tp_curve != {k: v["found"] for k, v in want["transplant"].items()}:
        print(f"does not reproduce fusion.json: {key_curve} {tp_curve}", file=sys.stderr)
        return 2

    union = set()
    for s in fold_scores.values():
        union |= {int(i) for i in np.argsort(-s, kind="stable")[: a.transplant_top]}
    OUT.mkdir(parents=True, exist_ok=True)
    rr.write_json(OUT / "candidates_combined.json", {
        "run": "item 14 combined list: the better of frozen-v1 and the leave-one-site-out re-ranker; chosen after seeing item 13's result",
        "strips": strips, "key_curve": key_curve, "key_ranks": ranks, "transplant_curve": tp_curve,
        "transplant_at_rate": {"area_km2": area, "rates": dict(rate_list), "no_texture": sorted(no_texture)},
    })
    np.savez(OUT / "transplant_folds.npz", **fold_scores)
    rr.write_json(OUT / "transplant_detections.json", {"detections": t["detections"], "truths": t["truths"]})
    rr.write_json(OUT / "transplant_votes.json", {"top_per_fold": a.transplant_top, "n": len(union), "detections": sorted(union)})
    print(f"key {key_curve}; transplant {tp_curve}; strips {len(strips)}; transplant vote set {len(union)} of {len(det_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
