"""Item 14a: the orderings of docs/proposals/vote-order-v1.md on the key and transplant boards, from recorded votes, no model call.

    uv run experiments/vote_orderings.py --run out/deep14 --out docs/reports/2026-10-31-vote-orderings/orderings.json

Post hoc, on tuning sites. frozen-v1, combined and combined + vote rule must equal item 14's summary, or nothing is written.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deep14_summary import INPUTS, demoted, load_records, rm, rr, tp  # noqa: E402
from landers.score import recall_at_false_alarm_rate  # noqa: E402

TOP = 100
FACTOR = 4.0
SENSITIVITY = (2.0, 8.0)


def first_hardware(rec: dict) -> bool:
    v = rec["votes"][0]
    return v["verdict"] == "hardware" and not v.get("off_schema")


def signed(rec: dict) -> float:
    """The mean over the votes of +confidence for hardware, -confidence for natural, 0 for unsure or off schema."""
    sign = {"hardware": 1.0, "natural": -1.0}
    return float(np.mean([0.0 if v.get("off_schema") else sign.get(v["verdict"], 0.0) * v["confidence"] for v in rec["votes"]]))


def order_a(depths: list[int], recs: dict[int, dict]) -> list[int]:
    """Depths (0-based, best first) with every first-vote hardware inside the top 100 ahead of the rest."""
    up = [d for d in depths if d < TOP and d in recs and first_hardware(recs[d])]
    ups = set(up)
    return up + [d for d in depths if d not in ups]


def order_b(depths: list[int], recs: dict[int, dict], factor: float = FACTOR) -> list[int]:
    """Depths sorted by depth * factor ** (-s), with depth counted from 1; a tie goes to the better depth."""
    def key(d: int) -> tuple[float, int]:
        k = float(d + 1)
        if d < TOP and d in recs:
            k *= factor ** (-signed(recs[d]))
        return k, d

    return sorted(depths, key=key)


def relist(rows: list[dict], order: list[int]) -> list[dict]:
    """The rows with scores that give this order."""
    n = len(order)
    return [{**rows[d], "score": float(n - i)} for i, d in enumerate(order)]


def key_board(data: dict, run_dir: Path, answers: dict, thresholds: dict) -> dict:
    lists = {sid: s["candidates"] for sid, s in data["strips"].items()}
    board: dict = {"frozen_v1": {sid: [{**r, "score": -float(r["frozen_rank"])} for r in rows] for sid, rows in lists.items()},
                   "combined": lists, "combined_votes": {}, "a": {}, "a_votes": {}, "b": {}}
    board |= {f"b_factor_{f:g}": {} for f in SENSITIVITY}
    counts = {}
    for sid, rows in lists.items():
        recs = {int(r["id"][1:]): r for r in load_records(run_dir / f"votes_{sid}.json")}
        low = {i for i, r in recs.items() if r["grade_after"] != r["grade_before"]}
        depths = list(range(len(rows)))
        a_order = order_a(depths, recs)
        board["combined_votes"][sid] = demoted(rows, low)
        board["a"][sid] = relist(rows, a_order)
        board["a_votes"][sid] = relist(rows, [d for d in a_order if d not in low] + [d for d in a_order if d in low])
        board["b"][sid] = relist(rows, order_b(depths, recs))
        for f in SENSITIVITY:
            board[f"b_factor_{f:g}"][sid] = relist(rows, order_b(depths, recs, f))
        counts[sid] = {"voted": len(recs), "first_hardware": sum(first_hardware(r) for r in recs.values()),
                       "first_natural": sum(r["votes"][0]["verdict"] == "natural" for r in recs.values()),
                       "first_unsure": sum(r["votes"][0]["verdict"] == "unsure" for r in recs.values()),
                       "off_schema_votes": sum(bool(v.get("off_schema")) for r in recs.values() for v in r["votes"]), "lowered": len(low)}
    ranks = {name: rr.key_ranks(ls, answers, thresholds) for name, ls in board.items()}
    return {"ranks": ranks, "vote_counts": counts}


def per_truth(dets: list[dict], truths: list[dict], area: float, fa: float) -> dict[int, bool]:
    """row_index of each truth -> found at this false-alarm rate, by the board's own function."""
    r = recall_at_false_alarm_rate(dets, truths, area, 20.0, fa, group=lambda t: (str(t["row_index"]), "x"))
    return {int(x["kind"]): bool(x["found"]) for x in r["rows"]}


def transplant_board(data: dict, run_dir: Path) -> dict:
    t = rr.load(INPUTS / "transplant_detections.json")
    folds = np.load(INPUTS / "transplant_folds.npz")
    rate = data["transplant_at_rate"]
    dets, truths, area = t["detections"], t["truths"], rate["area_km2"]
    recs = {r["detection"]: r for r in load_records(run_dir / "votes_transplant.json")}
    low = {i for i, r in recs.items() if r["grade_after"] != r["grade_before"]}
    frozen = np.array([float(d["score"]) for d in dets])
    names = ["frozen_v1", "combined", "combined_votes", "a", "a_votes", "b"] + [f"b_factor_{f:g}" for f in SENSITIVITY] + ["a_rate_depth", "b_rate_depth"]
    by_tile: dict = {}
    for x in truths:
        by_tile.setdefault(x["tile"], []).append(x)
    on_truth = [any(np.hypot(d["row"] - x["row"], d["col"] - x["col"]) <= float(x["radius_px"]) for x in by_tile.get(d["tile"], [])) for d in dets]
    allowed_n100 = int(np.floor(rate["rates"]["N100"] * area))
    rate_depths = {}
    found: dict = {name: {k: {} for k in rate["rates"]} for name in names}
    for site in folds.files:
        s = folds[site]
        best = np.argsort(-s, kind="stable")
        depth_of = {int(i): d for d, i in enumerate(best)}
        fold_recs = {d: recs[int(best[d])] for d in range(TOP) if int(best[d]) in recs}
        missing = [d for d in range(TOP) if int(best[d]) not in recs]
        assert not missing, f"{site}: fold's top {TOP} is not all voted"
        depths = list(range(len(best)))
        a_order = order_a(depths, fold_recs)
        low_depths = {depth_of[i] for i in low}

        def scored(order: list[int]) -> np.ndarray:
            out = np.zeros(len(best))
            for pos, d in enumerate(order):
                out[best[d]] = float(len(order) - pos)
            return out

        votes_all = s.copy()
        votes_all[list(low)] -= s.max() - s.min() + 1.0
        scores = {"frozen_v1": frozen, "combined": s, "combined_votes": votes_all, "a": scored(a_order),
                  "a_votes": scored([d for d in a_order if d not in low_depths] + [d for d in a_order if d in low_depths]),
                  "b": scored(order_b(depths, fold_recs))}
        scores |= {f"b_factor_{f:g}": scored(order_b(depths, fold_recs, f)) for f in SENSITIVITY}
        # added after seeing the board, not in the proposal: votes count only down to the N100 false-alarm rate, the depth by rate
        # that a strip's top 100 has on the key
        n_fa, cut = 0, TOP
        for d, i in enumerate(best):
            n_fa += not on_truth[int(i)]
            if n_fa > allowed_n100:
                cut = min(d, TOP)
                break
        rate_depths[site] = cut
        rate_recs = {d: r for d, r in fold_recs.items() if d < cut}
        scores |= {"a_rate_depth": scored(order_a(depths, rate_recs)), "b_rate_depth": scored(order_b(depths, rate_recs))}
        site_truths = {x["row_index"] for x in truths if x["site"] == site}
        for name, sc in scores.items():
            listed = [{**d, "score": float(v)} for d, v in zip(dets, sc, strict=True)]
            for k, fa in rate["rates"].items():
                got = per_truth(listed, truths, area, fa)
                found[name][k] |= {i: got[i] for i in site_truths}
    return {"found": found, "truths": truths, "lowered_detections": sorted(low), "rate_depths": rate_depths, "allowed_false_alarms": {k: int(np.floor(fa * area)) for k, fa in rate["rates"].items()},
            "area_km2": area, "vote_counts": {"voted": len(recs), "first_hardware": sum(first_hardware(r) for r in recs.values()),
                                              "first_natural": sum(r["votes"][0]["verdict"] == "natural" for r in recs.values()),
                                              "first_unsure": sum(r["votes"][0]["verdict"] == "unsure" for r in recs.values()), "lowered": len(low)}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run_dir, out = Path(a.run), Path(a.out)
    sites, thresholds, answers = rr.controls()
    data = rr.load(INPUTS / "candidates_combined.json")
    pieces = {f"{p['site']}/{p['piece']}/{p['strip']}": p for p in tp.key_pieces(answers, thresholds, tp.tuning_sources(sites))}
    summary = rr.load(run_dir / "summary.json")

    k = key_board(data, run_dir, answers, thresholds)
    tb = transplant_board(data, run_dir)
    key_out, tp_out = {}, {}
    for name, ranks in k["ranks"].items():
        c = rr.curve(ranks.values())
        key_out[name] = {"n": len(ranks), "curve": c, "interval_95": {n: rm.wilson(v, len(ranks)) for n, v in c.items()}}
    for name, per in tb["found"].items():
        tp_out[name] = {}
        for rate_name, got in per.items():
            f = sum(got.values())
            tp_out[name][rate_name] = {"found": f, "n": len(got), "interval_95": rm.wilson(f, len(got))}

    # the rows item 14 published must come out the same here
    for name in ("frozen_v1", "combined", "combined_votes"):
        assert key_out[name]["curve"] == summary["key"][name]["curve"], f"key {name}"
        for rate_name, row in tp_out[name].items():
            assert row["found"] == summary["transplant"][name][rate_name]["found"], f"transplant {name} {rate_name}"

    moved_key, moved_tp = {}, {}
    truth_of = {x["row_index"]: x for x in tb["truths"]}
    inside = lambda r: r is not None and r <= 20  # noqa: E731
    desc = lambda i: {f: truth_of[i][f] for f in ("site", "piece", "kind", "size_m", "target")} | {"truth": i}  # noqa: E731
    for name in tb["found"]:
        if name == "combined":
            continue
        b20, o20 = tb["found"]["combined"]["N20"], tb["found"][name]["N20"]
        moved_tp[name] = {"out": [desc(i) for i in sorted(b20) if b20[i] and not o20[i]], "in": [desc(i) for i in sorted(b20) if o20[i] and not b20[i]]}
        if name not in k["ranks"]:
            continue
        base, other = k["ranks"]["combined"], k["ranks"][name]
        moved_key[name] = {"out": [{"piece": p, "kind": pieces[p]["kind"], "combined": base[p], "here": other[p]} for p in sorted(base) if inside(base[p]) and not inside(other[p])],
                           "in": [{"piece": p, "kind": pieces[p]["kind"], "combined": base[p], "here": other[p]} for p in sorted(base) if inside(other[p]) and not inside(base[p])]}

    result = {"run": "item 14a: post hoc orderings on tuning sites, rules in docs/proposals/vote-order-v1.md; only the blind run can judge them; the four sites sealed for frozen-v1 are not blind",
              "key": key_out, "transplant": tp_out, "transplant_allowed_false_alarms": tb["allowed_false_alarms"], "transplant_area_km2": tb["area_km2"], "rate_depths_added_after_seeing_the_board": tb["rate_depths"],
              "found_truths": {name: {r: sorted(i for i, f in tb["found"][name][r].items() if f) for r in tb["found"][name]} for name in ("combined", "combined_votes")},
              "moved_key": moved_key, "moved_transplant": moved_tp, "key_ranks": k["ranks"], "vote_counts": {"key": k["vote_counts"], "transplant": tb["vote_counts"]}}
    out.parent.mkdir(parents=True, exist_ok=True)
    rr.write_json(out, result)
    show = ["frozen_v1", "combined", "combined_votes", "a", "a_votes", "b"]
    for name in show:
        print(name, "key", key_out[name]["curve"], "transplant", {r: v["found"] for r, v in tp_out[name].items()})
    for name in ("a_rate_depth", "b_rate_depth"):
        print(name, json.dumps({r: v["found"] for r, v in tp_out[name].items()}), "out", len(moved_tp[name]["out"]), "in", len(moved_tp[name]["in"]))
    print("rate depths", tb["rate_depths"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
