"""Diagnostics beside the first score: why each recorded piece ranks where it does.

    uv run experiments/first_score_diag.py out/baseline_v1/candidates_baseline_v1.json \
        --threshold-file out/inject_eval_p1_cal.json --out out/baseline_v1/score_baseline_v1_diag.json

Does not change the score (landers/score.py, thresholds.json and tuning.json are read, never written).
For every recorded piece in the run: the matched candidate's calibrated and raw score, its whole-strip rank
(the scored number), its rank within a local area around the recorded position (the contact-sheet view),
its rank within its own branch, and whether it clears the operating-point threshold that the phase 1
injection evaluation fixed for 2 false alarms per km2. For a miss: the nearest candidate at any distance.
Then recall at several N, so the gap to the pass line can be read off.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.score import load_json, match_radius_px  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--threshold-file", default=None, help="injection eval file carrying score_threshold")
    ap.add_argument("--local-radius-m", type=float, default=1500.0)
    ap.add_argument("--at-n", default="10,20,50,100,250,1000,5000")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    cands = load_json(a.candidates)
    answers = load_json(a.answers)
    thresholds = load_json(a.thresholds)
    op_threshold = None
    if a.threshold_file:
        op_threshold = load_json(a.threshold_file).get("score_threshold")
    strips = cands["strips"]
    at_n = [int(x) for x in a.at_n.split(",")]

    sorted_by_strip = {
        sid: sorted(e["candidates"], key=lambda c: -float(c.get("score", 0.0))) for sid, e in strips.items()
    }

    pieces = []
    for site in answers["sites"]:
        for pc in site["pieces"]:
            if pc.get("line") is None or pc.get("sample") is None or pc.get("strip") is None:
                continue
            sid = pc["strip"]
            if sid not in strips:
                continue
            scale = float(strips[sid].get("scale_m", 0.25))
            radius = match_radius_px(thresholds, scale)
            local_r = a.local_radius_m / scale
            row, col = float(pc["line"]) - 1.0, float(pc["sample"]) - 1.0
            ranked = sorted_by_strip[sid]
            hit = None
            hit_rank = None
            local_rank = 0
            branch_rank = 0
            nearest = None
            n_within_radius = 0
            within_2r = []
            for i, c in enumerate(ranked, start=1):
                d = math.hypot(float(c["row"]) - row, float(c["col"]) - col)
                if nearest is None or d < nearest[0]:
                    nearest = (d, c)
                if d <= radius:
                    n_within_radius += 1
                if d <= 2 * radius and len(within_2r) < 12:
                    within_2r.append(
                        {
                            "rank": i,
                            "branch": c.get("branch"),
                            "score": c.get("score"),
                            "raw_score": (c.get("extra") or {}).get("raw_score"),
                            "distance_px": round(d, 1),
                            "area_px": c.get("area_px"),
                        }
                    )
                if hit is None:
                    if d <= local_r:
                        local_rank += 1
                    if d <= radius:
                        hit, hit_rank = c, i
                        branch_rank = sum(1 for x in ranked[:i] if x.get("branch") == c.get("branch"))
            rec = {
                "site": site["name"],
                "piece": pc["piece"],
                "strip": sid,
                "size_m": pc.get("size_m"),
                "rank": hit_rank,
                "local_rank": local_rank if hit is not None else None,
                "branch_rank": branch_rank if hit is not None else None,
                "n_candidates_within_radius": n_within_radius,
                "within_2x_radius_by_score": within_2r,
                "matched": None
                if hit is None
                else {
                    "branch": hit.get("branch"),
                    "score": hit.get("score"),
                    "raw_score": (hit.get("extra") or {}).get("raw_score"),
                    "area_px": hit.get("area_px"),
                    "distance_px": round(math.hypot(float(hit["row"]) - row, float(hit["col"]) - col), 1),
                    "also": (hit.get("extra") or {}).get("also"),
                    "above_operating_threshold": None
                    if op_threshold is None
                    else float(hit.get("score", 0.0)) > float(op_threshold),
                },
                "nearest_any": None
                if nearest is None
                else {
                    "distance_px": round(nearest[0], 1),
                    "distance_m": round(nearest[0] * scale, 1),
                    "branch": nearest[1].get("branch"),
                    "score": nearest[1].get("score"),
                    "rank": ranked.index(nearest[1]) + 1,
                },
            }
            pieces.append(rec)

    scored_ranks = [p["rank"] for p in pieces]
    recall_at = {
        str(n): {
            "found": sum(1 for r in scored_ranks if r is not None and r <= n),
            "of": len(scored_ranks),
            "recall": round(sum(1 for r in scored_ranks if r is not None and r <= n) / len(scored_ranks), 3)
            if scored_ranks
            else None,
        }
        for n in at_n
    }

    per_strip = {}
    for sid, ranked in sorted_by_strip.items():
        area = float(strips[sid].get("valid_area_km2") or 0.0)
        above = None if op_threshold is None else sum(1 for c in ranked if float(c.get("score", 0.0)) > op_threshold)
        per_strip[sid] = {
            "n_candidates": len(ranked),
            "valid_area_km2": area,
            "n_above_operating_threshold": above,
            "above_per_km2": None if above is None or area <= 0 else round(above / area, 2),
            "pieces_above_operating_threshold": sum(
                1
                for p in pieces
                if p["strip"] == sid and p["matched"] and p["matched"]["above_operating_threshold"]
            ),
            "pieces_recorded": sum(1 for p in pieces if p["strip"] == sid),
        }

    out = {
        "run": cands.get("run"),
        "git_commit": cands.get("git_commit"),
        "candidates_file": a.candidates,
        "answers_file": a.answers,
        "thresholds_file": a.thresholds,
        "operating_threshold": op_threshold,
        "operating_threshold_file": a.threshold_file,
        "local_radius_m": a.local_radius_m,
        "pieces": pieces,
        "recall_at": recall_at,
        "strips": per_strip,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))

    print(f"{'site':13s} {'piece':14s} {'rank':>6s} {'local':>6s} {'brrank':>6s} {'score':>6s} {'raw':>6s}  branch   >op  nearest(m, branch, score)")
    for p in pieces:
        m = p["matched"]
        nn = p["nearest_any"]
        near = f"{nn['distance_m']:.1f} {nn['branch']} {nn['score']}" if nn else "-"
        if m:
            print(
                f"{p['site']:13s} {p['piece']:14s} {p['rank']:6d} {p['local_rank']:6d} {p['branch_rank']:6d} "
                f"{m['score']:6.2f} {str(m['raw_score']):>6s}  {m['branch']:12s} {str(m['above_operating_threshold']):5s} {near}"
            )
        else:
            print(f"{p['site']:13s} {p['piece']:14s} {'-':>6s} {'-':>6s} {'-':>6s} {'-':>6s} {'-':>6s}  {'-':12s} {'-':5s} {near}")
    print()
    print("recall at N (whole-strip rank):", {n: f"{v['found']}/{v['of']}" for n, v in recall_at.items()})
    print()
    print(f"{'strip':16s} {'cands':>7s} {'>op':>6s} {'>op/km2':>8s} {'pieces>op':>10s}")
    for sid, s in per_strip.items():
        print(f"{sid:16s} {s['n_candidates']:7d} {str(s['n_above_operating_threshold']):>6s} {str(s['above_per_km2']):>8s} {s['pieces_above_operating_threshold']:4d}/{s['pieces_recorded']}")
    print(f"\nwritten: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
