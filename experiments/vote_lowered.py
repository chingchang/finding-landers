"""Item 14a: what item 14's votes and reviews lowered, from the records, no model call and no heldout strip.

    uv run experiments/vote_lowered.py --run out/deep14 --out-dir docs/reports/2026-10-31-vote-orderings

Writes lowered.json (each lowered transplant detection, whether it sits on a planted piece or a sham, its branch and size, its
votes; the Spark verdicts on recorded pieces; first votes on pieces and on the rest) and lowered_planted.png (the crops, from
the planted tiles of out/rerank/t10, one stretch per sheet).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deep14_run import TileBank  # noqa: E402
from deep14_summary import INPUTS, load_records, match_radius_px, on_piece, rr, tp  # noqa: E402

SHEET_CROP, ZOOM, PER_ROW = 64, 3, 8


def first_vote(rec: dict) -> str:
    return rec["votes"][0]["verdict"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    run_dir, out = Path(a.run), Path(a.out_dir)
    sites, thresholds, answers = rr.controls()
    data = rr.load(INPUTS / "candidates_combined.json")
    pieces = tp.key_pieces(answers, thresholds, tp.tuning_sources(sites))
    t = rr.load(INPUTS / "transplant_detections.json")
    dets, truths = t["detections"], t["truths"]
    folds = np.load(INPUTS / "transplant_folds.npz")
    depth = {site: {int(i): d + 1 for d, i in enumerate(np.argsort(-folds[site], kind="stable"))} for site in folds.files}

    found = rr.load(out / "orderings.json")["found_truths"]
    cuts = rr.load(rr.RUN / "run.json")["cuts"]
    placements: dict = {}

    def planted_at(d: dict) -> list[dict]:
        return [x for x in truths if x["tile"] == d["tile"] and np.hypot(d["row"] - x["row"], d["col"] - x["col"]) <= float(x["radius_px"])]

    def sham_at(d: dict) -> list[str]:
        """Sham cuts (ground pasted the same way as a piece) inside the radius their piece would have."""
        tile = d["tile"]
        if tile not in placements:
            placements[tile] = rr.load(rr.RUN / "tiles" / (tile.replace(":", "_") + ".json"))["placements"]
        return [f"{p['site']}/{p['piece']}" for p in placements[tile] if p["sham"]
                and np.hypot(d["row"] - p["row"], d["col"] - p["col"]) <= match_radius_px(thresholds, cuts[p["cut_index"]]["scale_m"], p["kind"])]

    def what_is(d: dict) -> str:
        return "planted" if planted_at(d) else "sham" if sham_at(d) else "other"

    recs = load_records(run_dir / "votes_transplant.json")
    lowered = []
    for r in recs:
        if r["grade_after"] == r["grade_before"]:
            continue
        d = dets[r["detection"]]
        on = planted_at(d)
        own = [site for site in folds.files if any(x["site"] == site for x in on)]
        lowered.append({"detection": r["detection"], "tile": d["tile"], "row": d["row"], "col": d["col"], "branch": d["branch"], "area_px": d["area_px"],
                        "on_planted": [{k: x[k] for k in ("site", "piece", "kind", "size_m", "target")} | {"truth": x["row_index"], "distance_px": round(float(np.hypot(d["row"] - x["row"], d["col"] - x["col"])), 1), "radius_px": x["radius_px"],
                                                                                                  "found_combined": [n for n, f in found["combined"].items() if x["row_index"] in f], "found_with_vote_rule": [n for n, f in found["combined_votes"].items() if x["row_index"] in f]} for x in on],
                        "on_sham": sham_at(d),
                        "depth_in_own_fold": min((depth[s][r["detection"]] for s in own), default=None), "best_depth_any_fold": min(depth[s][r["detection"]] for s in folds.files),
                        "votes": [{k: v[k] for k in ("verdict", "confidence", "reason")} for v in r["votes"]], "valid_fraction": r["crops"][0]["valid_fraction"]})
    lowered.sort(key=lambda x: (not x["on_planted"], x["best_depth_any_fold"]))

    # first votes, split by what the row is
    planted_first, key_first = Counter(), Counter()
    for r in recs:
        planted_first[(what_is(dets[r["detection"]]), first_vote(r))] += 1
    review_rows = []
    for sid, s in data["strips"].items():
        rows = s["candidates"]
        hits = on_piece(rows, [p for p in pieces if p["strip"] == sid], s["scale_m"], thresholds)
        by_id = {r["id"]: r for r in load_records(run_dir / f"votes_{sid}.json")}
        for rid, r in by_id.items():
            key_first[("piece" if int(rid[1:]) in hits else "other", first_vote(r))] += 1
        rev = rr.load(run_dir / f"review_{sid}.json")
        for cid, v in rev["verdicts"].items():
            i = rev["ranks"][int(cid[1:])]
            if v["action"] == "lower" and i in hits:
                review_rows.append({"strip": sid, "rank": i + 1, "pieces": hits[i], "branch": rows[i]["branch"], "verdict": v, "first_vote": {k: by_id[f"c{i:03d}"]["votes"][0][k] for k in ("verdict", "confidence")}})

    summary = rr.load(run_dir / "summary.json")
    ledger = rr.load(run_dir / "ledger.json")
    votes_n, cands_n = sum(s["votes"] for s in summary["per_strip"].values()), sum(s["voted"] for s in summary["per_strip"].values())
    wonder = ledger["entries"]["wonder"]
    # placement files are per tile; every detection of the board is checked once, for the count of detections on a sham
    on_sham_all = sum(bool(sham_at(d)) for d in dets)
    n_sham = sum(p["sham"] for tile in {d["tile"] for d in dets} for p in rr.load(rr.RUN / "tiles" / (tile.replace(":", "_") + ".json"))["placements"])
    rr.write_json(out / "lowered.json", {
        "price_check": {"key_candidates": cands_n, "key_votes": votes_n, "votes_per_candidate": round(votes_n / cands_n, 3), "band_share": summary["band_share"],
                        "wonder_calls": wonder["units"], "wonder_usd": wonder["cost_usd"], "usd_per_wonder_call": round(wonder["cost_usd"] / wonder["units"], 5), "spark_usd": ledger["entries"]["spark"]["cost_usd"], "this_run_usd": ledger["total_cost_usd"], "all_runs_usd": round(ledger["prior_usd"] + ledger["total_cost_usd"], 4)},
        "review_totals": {"verdicts": sum(s["review_verdicts"] for s in summary["per_strip"].values()), "lowered_beyond_votes": sum(s["lowered_by_review"] for s in summary["per_strip"].values())},
        "shams": {"placements_on_tiles_with_a_detection": n_sham, "detections_on_a_sham": on_sham_all},
        "what": "item 14's lowered transplant detections and Spark's lowered rows on recorded pieces; 128 is both the number of planted pieces and, separately, the number of detections voted on",
        "transplant_voted": len(recs), "transplant_lowered": len(lowered), "lowered_on_planted": sum(bool(x["on_planted"]) for x in lowered), "lowered_on_sham": sum(bool(x["on_sham"]) for x in lowered), "planted_pieces": len(truths),
        "distinct_planted_pieces_under_a_lowered_detection": len({p["truth"] for x in lowered for p in x["on_planted"]}),
        "planted_pieces_with_a_voted_detection": len({x["row_index"] for r in recs for x in planted_at(dets[r["detection"]])}),
        "first_votes_transplant": {f"{k[0]}/{k[1]}": v for k, v in sorted(planted_first.items())}, "first_votes_key_lists": {f"{k[0]}/{k[1]}": v for k, v in sorted(key_first.items())},
        "lowered": lowered, "review_lowered_recorded_rows": review_rows})

    # the sheet: every lowered detection on a planted piece, then the rest
    bank = TileBank()
    crops = [bank.read_at(dets[x["detection"]], SHEET_CROP)[0] for x in lowered]
    good = np.concatenate([c[c > 0] for c in crops]) if crops else np.array([1.0])
    lo, hi = np.percentile(good, [0.5, 99.9])
    cell = SHEET_CROP * ZOOM
    n_rows = (len(crops) + PER_ROW - 1) // PER_ROW
    sheet = Image.new("L", (PER_ROW * (cell + 4), n_rows * (cell + 16)), 0)
    draw = ImageDraw.Draw(sheet)
    for i, (x, c) in enumerate(zip(lowered, crops, strict=True)):
        g = np.clip((c - lo) / (hi - lo), 0, 1) * 255
        im = Image.fromarray(g.astype(np.uint8)).resize((cell, cell), Image.NEAREST)
        px, py = (i % PER_ROW) * (cell + 4), (i // PER_ROW) * (cell + 16)
        sheet.paste(im, (px, py + 14))
        draw.text((px + 1, py), f"{i + 1} {'P' if x['on_planted'] else 'S' if x['on_sham'] else '-'} {x['branch'][:6]} {x['area_px']}", fill=255)
    sheet.save(out / "lowered_planted.png")
    print(f"lowered {len(lowered)}, on a planted piece {sum(bool(x['on_planted']) for x in lowered)}")
    print(dict(planted_first), dict(key_first))
    for i, x in enumerate(lowered):
        print(i + 1, x["branch"], x["area_px"], x["valid_fraction"], x["depth_in_own_fold"], x["best_depth_any_fold"], [(p["site"], p["piece"], p["size_m"], p["truth"], p["distance_px"], p["found_combined"], p["found_with_vote_rule"]) for p in x["on_planted"]], x["on_sham"], [(v["verdict"], v["confidence"]) for v in x["votes"]])
    for r in review_rows:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
