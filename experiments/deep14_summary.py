"""What item 14's votes did, from a run's records, no model call. The measures are fixed in
docs/proposals/vote-single-v1.md.

    uv run experiments/deep14_summary.py --run out/deep14 --no-texture ID ID

Every board is shown before and after: frozen-v1, the combined list, the combined list with the votes applied, and with the
review applied too. A lowered candidate goes below everything kept and stays on the list. Writes <run>/summary.json.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import rerank as rr  # noqa: E402

from landers import transplant as tp  # noqa: E402
from landers.models.run import candidate_id  # noqa: E402
from landers.rerank import model as rm  # noqa: E402
from landers.score import match_radius_px  # noqa: E402

INPUTS = rr.config.REPO_ROOT / "out" / "deep14" / "inputs"
FLAG_SHARE = 0.9


def load_records(path: Path) -> list[dict]:
    return rr.load(path)["records"] if path.exists() else []


def demoted(rows: list[dict], lowered: set[int]) -> list[dict]:
    """The list with the lowered rows moved below every other row, each row's order otherwise kept."""
    floor = min(r["score"] for r in rows)
    span = max(r["score"] for r in rows) - floor + 1.0
    return [{**r, "score": r["score"] - span if i in lowered else r["score"]} for i, r in enumerate(rows)]


def on_piece(rows: list[dict], pieces: list[dict], scale: float, thresholds: dict) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for i, r in enumerate(rows):
        for p in pieces:
            if np.hypot(r["row"] - p["row"], r["col"] - p["col"]) <= match_radius_px(thresholds, scale, p["kind"]):
                out.setdefault(i, []).append(p["piece"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--no-texture", nargs="*", default=[])
    a = ap.parse_args()
    run_dir = Path(a.run)
    sites, thresholds, answers = rr.controls()
    data = rr.load(INPUTS / "candidates_combined.json")
    pieces = tp.key_pieces(answers, thresholds, tp.tuning_sources(sites))

    lists = {sid: s["candidates"] for sid, s in data["strips"].items()}
    frozen_lists = {sid: [{**r, "score": -float(r["frozen_rank"])} for r in rows] for sid, rows in lists.items()}
    after_votes, after_review, per_strip, lowered_pieces = {}, {}, {}, []
    for sid, rows in lists.items():
        recs = load_records(run_dir / f"votes_{sid}.json")
        low = {int(r["id"][1:]) for r in recs if r["grade_after"] != r["grade_before"]}
        n_votes = sum(len(r["votes"]) for r in recs)
        band = sum(len(r["votes"]) > 1 for r in recs)
        rev = run_dir / f"review_{sid}.json"
        by_review = set()
        verdicts = 0
        stopped = None
        if rev.exists():
            d = rr.load(rev)
            ranks = d["ranks"]
            verdicts, stopped = len(d["verdicts"]), d["stopped"]
            by_review = {ranks[int(cid[1:])] for cid, v in d["verdicts"].items() if v["action"] == "lower"}
        after_votes[sid] = demoted(rows, low)
        after_review[sid] = demoted(rows, low | by_review)
        scale = data["strips"][sid]["scale_m"]
        plist = [p for p in pieces if p["strip"] == sid]
        hits = on_piece(rows, plist, scale, thresholds)
        for i in sorted((low | by_review) & set(hits)):
            rec = next((r for r in recs if r["id"] == candidate_id(i)), None)
            lowered_pieces.append({"strip": sid, "rank": i + 1, "pieces": hits[i], "by": "votes" if i in low else "review",
                                   "votes": [(v["verdict"], v["confidence"]) for v in rec["votes"]] if rec else []})
        cleared = []
        for p in plist:
            at = [i for i, h in hits.items() if p["piece"] in h]
            if not at:
                cleared.append({"piece": p["piece"], "listed": False})
                continue
            top = min(at)
            above = [i for i in range(top) if i not in hits]
            cleared.append({"piece": p["piece"], "listed": True, "rank_before": top + 1, "false_alarms_above": len(above),
                            "voted_above": sum(1 for i in above if i < len(recs)), "cleared_above": sum(i in low | by_review for i in above)})
        per_strip[sid] = {"site": data["strips"][sid]["site"], "voted": len(recs), "votes": n_votes, "band": band, "lowered_by_votes": len(low),
                          "share_lowered": round(len(low) / len(recs), 3) if recs else None, "flag_over_share": bool(recs and len(low) / len(recs) > FLAG_SHARE),
                          "review_stopped": stopped, "review_verdicts": verdicts, "lowered_by_review": len(by_review - low), "pieces": cleared}

    board = {"frozen_v1": frozen_lists, "combined": lists, "combined_votes": after_votes, "combined_votes_review": after_review}
    ranks_of = {name: rr.key_ranks(ls, answers, thresholds) for name, ls in board.items()}
    key = {name: {"curve": rr.curve(r.values()), "n": len(r), "interval_95_at_20": rm.wilson(rr.curve(r.values())["20"], len(r))} for name, r in ranks_of.items()}
    moves = {k: {name: ranks_of[name].get(k) for name in board} for k in ranks_of["combined"]}
    rises = sorted(k for k, m in moves.items() if not (m["combined"] and m["combined"] <= 20) and m["combined_votes_review"] and m["combined_votes_review"] <= 20)
    drops = sorted(k for k, m in moves.items() if m["combined"] and m["combined"] <= 20 and not (m["combined_votes_review"] and m["combined_votes_review"] <= 20))

    t = rr.load(INPUTS / "transplant_detections.json")
    folds = np.load(INPUTS / "transplant_folds.npz")
    rate = data["transplant_at_rate"]
    tp_recs = load_records(run_dir / "votes_transplant.json")
    tp_low = {r["detection"] for r in tp_recs if r["grade_after"] != r["grade_before"]}
    frozen_det = {i: float(d["score"]) for i, d in enumerate(t["detections"])}
    no_texture = set(a.no_texture or rate["no_texture"])
    area = rate["area_km2"]

    def transplant_board(score_of) -> dict:
        found: dict = {k: [] for k in rate["rates"]}
        for site in folds.files:
            s = score_of(site)
            dets = [{**d, "score": float(v)} for d, v in zip(t["detections"], s, strict=True)]
            for name, fa in rate["rates"].items():
                found[name] += [x for x in rr.transplant_rows(dets, t["truths"], area, fa, no_texture) if x["site"] == site]
        return {k: {"found": rr.summarise(v)["found"], "n": rr.summarise(v)["n"], "by_ground": rr.summarise(v)["by_ground"]} for k, v in found.items()}

    def with_votes(site):
        s = folds[site].copy()
        span = s.max() - s.min() + 1.0
        s[list(tp_low)] -= span
        return s

    frozen_scores = np.array([frozen_det[i] for i in range(len(t["detections"]))])
    transplant = {"frozen_v1": transplant_board(lambda _: frozen_scores), "combined": transplant_board(lambda site: folds[site]), "combined_votes": transplant_board(with_votes)}

    ledger = rr.load(run_dir / "ledger.json")
    out = {
        "not_blind": "tuning sites; the four sealed for frozen-v1 are not blind; the combined list was chosen after seeing item 13's result",
        "backend": ledger["backend"], "ledger_usd": ledger["total_cost_usd"], "prior_usd": ledger.get("prior_usd"),
        "key": key, "rises_into_top_20": rises, "drops_from_top_20": drops, "pieces_lowered": lowered_pieces, "piece_ranks": moves, "per_strip": per_strip,
        "transplant": transplant, "transplant_votes": {"voted": len(tp_recs), "votes": sum(len(r["votes"]) for r in tp_recs), "lowered": len(tp_low)},
        "band_share": round(statistics.mean(s["band"] / s["voted"] for s in per_strip.values() if s["voted"]), 3) if any(s["voted"] for s in per_strip.values()) else None,
    }
    rr.write_json(run_dir / "summary.json", out)
    print(json.dumps({k: out[k] for k in ("backend", "ledger_usd", "key", "rises_into_top_20", "drops_from_top_20", "pieces_lowered", "transplant_votes", "band_share")}, indent=1))
    print({name: {k: v["found"] for k, v in b.items()} for name, b in transplant.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
