"""Scratch (item 8a): what calibration per strip does to the key run, offline, before any detector pass.

    uv run experiments/strip_calibration.py out/shape_v3/candidates_v03_features.json --out out/cal_strip/offline

Every candidate of the unruled v0.3 key run carries its raw branch score, so the per-strip curve of every
strip can be fitted from the run itself (landers.calibrate.fit_strip, the same code the v0.4 detector runs)
and applied offline. The only difference from a fresh pass is the tail: candidates below the v0 floor are not
in the file, so on strips where the v0 table overestimates rarity the per-strip list is missing its bottom.
That cannot touch the top 20 or anything above the operating point; deep ranks are lower bounds.

Prints, and writes to <out>/offline_strip_calibration.json:
- the key board with shape_v3 under the v0 table and under per-strip curves (top_exclude 0 and 20);
- per piece, the rank under each, and the rank among its branch on its strip (unchanged by construction);
- per strip, candidates per km2 above calibrated 0, 1 and 2 (1, 0.1, 0.01 false alarms per km2 if the
  scale is honest) under each calibration;
- a split-half check: curves fitted on the strip's even tiles applied to its odd tiles, realised rate
  against nominal at the same three levels.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.calibrate import fit_strip  # noqa: E402
from landers.detect import DetectorConfig  # noqa: E402
from landers.score import load_json, score  # noqa: E402
from landers.shape import ShapeRules, apply_rules_json  # noqa: E402

LEVELS = (0.0, 1.0, 2.0)
FLOOR = DetectorConfig().min_calibrated_score


def recalibrate(entry: dict, top_exclude: int) -> tuple[list[dict], dict]:
    cal = fit_strip(entry["candidates"], float(entry["valid_area_km2"]), "per_strip", top_exclude)
    out = []
    for c in entry["candidates"]:
        raw = float(c["extra"]["raw_score"])
        s = cal.calibrated(c["branch"], raw)
        if s < FLOOR:
            continue
        out.append({**c, "score": round(s, 3)})
    return out, cal.to_json()


def ruled(cands: list[dict], rules: ShapeRules) -> list[dict]:
    return [apply_rules_json(c, rules) for c in cands]


def above(cands: list[dict], area: float) -> dict:
    return {str(lv): round(sum(1 for c in cands if float(c["score"]) > lv) / area, 3) for lv in LEVELS}


def tile_phase(c: dict, stride: int) -> int:
    return (int(float(c["row"]) // stride) + int(float(c["col"]) // stride)) % 2


def split_half(entry: dict, stride: int, top_exclude: int) -> dict:
    """Fit on phase 0 candidates (half the area), apply to phase 1, realised rate above each level."""
    cands = entry["candidates"]
    half = float(entry["valid_area_km2"]) / 2.0
    p0 = [c for c in cands if tile_phase(c, stride) == 0]
    p1 = [c for c in cands if tile_phase(c, stride) == 1]
    if not p0 or not p1:
        return {}
    cal = fit_strip(p0, half, "half", top_exclude)
    scored = [cal.calibrated(c["branch"], float(c["extra"]["raw_score"])) for c in p1]
    return {
        "n_fit": len(p0),
        "n_test": len(p1),
        "realised_per_km2": {str(lv): round(sum(1 for s in scored if s > lv) / half, 3) for lv in LEVELS},
        "nominal_per_km2": {str(lv): 10 ** (-lv) for lv in LEVELS},
    }


def branch_rank(entry: dict, piece_row: float, piece_col: float, radius: float):
    """Rank of the best candidate within the radius among its branch's candidates on the strip, by raw score."""
    import math

    near = [
        c for c in entry["candidates"] if math.hypot(float(c["row"]) - piece_row, float(c["col"]) - piece_col) <= radius
    ]
    if not near:
        return None
    best = max(near, key=lambda c: float(c["score"]))
    same = [c for c in entry["candidates"] if c["branch"] == best["branch"]]
    raw = float(best["extra"]["raw_score"])
    return {
        "branch": best["branch"],
        "rank_in_branch": 1 + sum(1 for c in same if float(c["extra"]["raw_score"]) > raw),
        "n_branch": len(same),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key_candidates")
    ap.add_argument("--rules", default=str(config.REPO_ROOT / "landers" / "shape_v3.json"))
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--top-exclude", type=int, action="append", default=None)
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out" / "cal_strip" / "offline"))
    ap.add_argument(
        "--write-candidates",
        action="store_true",
        help="also write <out>/candidates_<variant>.json per per-strip variant: the unruled recalibrated run "
        "(detector config marked per_strip), for scripts/tune.py --candidate-key-candidates",
    )
    a = ap.parse_args(argv)
    excludes = a.top_exclude or [0, 20]

    run = load_json(a.key_candidates)
    answers, thresholds = load_json(a.answers), load_json(a.thresholds)
    rules = ShapeRules.load(a.rules)
    cfg = run["detector"]
    stride = int(cfg["tile"]) - int(cfg["overlap"])
    variants: dict[str, dict] = {}
    curves: dict[str, dict] = {}
    # reference: the v0 table as recorded in the run, shape_v3 applied offline
    variants["v0_table"] = {sid: {**e, "candidates": ruled(e["candidates"], rules)} for sid, e in run["strips"].items()}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for k in excludes:
        name = f"per_strip_top{k}"
        variants[name] = {}
        curves[name] = {}
        unruled: dict = {}
        for sid, e in run["strips"].items():
            cands, cal = recalibrate(e, k)
            unruled[sid] = {**e, "candidates": cands, "calibration": cal}
            variants[name][sid] = {**e, "candidates": ruled(cands, rules)}
        if a.write_candidates:
            det = {**cfg, "calibration": None, "calibration_mode": "per_strip", "calibration_top_exclude": k}
            doc = {**run, "run": f"{run.get('run')}_{name}", "detector": det, "strips": unruled}
            doc["recalibrated_from"] = a.key_candidates
            (out / f"candidates_{name}.json").write_text(json.dumps(doc))
            print(f"written: {out / f'candidates_{name}.json'}")
            curves[name][sid] = {
                b: {"n": c["n"], "top_raw": c["scores"][0], "slope": c["slope"]} for b, c in cal["branches"].items()
            }
    boards = {}
    for name, strips in variants.items():
        s = score({**run, "strips": strips}, answers, thresholds)
        boards[name] = {
            "recall_at_n": s.recall_at_n,
            "found": s.n_pieces_found,
            "recorded": s.n_pieces_recorded,
            "by_kind": s.recall_by_kind,
            "pieces": {f"{p.site}/{p.piece}": {"rank": p.rank, "branch": p.branch} for p in s.pieces},
            "strips": {t.strip: {"candidates": t.n_candidates, "fa_per_km2": t.false_alarms_per_km2} for t in s.strips},
            "above": {sid: above(e["candidates"], float(e["valid_area_km2"])) for sid, e in strips.items()},
        }
    # rank within branch (unchanged by any per-branch monotone calibration)
    from landers.score import match_radius_px

    in_branch = {}
    for site in answers["sites"]:
        for pc in site["pieces"]:
            if pc.get("line") is None:
                continue
            e = run["strips"].get(pc["strip"])
            if e is None:
                continue
            r = match_radius_px(thresholds, e["scale_m"], None)
            in_branch[f"{site['name']}/{pc['piece']}"] = branch_rank(e, pc["line"] - 1, pc["sample"] - 1, r)
    halves = {f"top{k}": {sid: split_half(e, stride, k) for sid, e in run["strips"].items()} for k in excludes}
    result = {
        "key_candidates": a.key_candidates,
        "rules": a.rules,
        "floor": FLOOR,
        "boards": boards,
        "rank_in_branch": in_branch,
        "curves": curves,
        "split_half": halves,
    }
    (out / "offline_strip_calibration.json").write_text(json.dumps(result, indent=1))

    names = list(boards)
    print(f"{'piece':28s} " + " ".join(f"{n:>16s}" for n in names) + "  in-branch")
    for key in boards[names[0]]["pieces"]:
        cells = []
        for n in names:
            p = boards[n]["pieces"][key]
            cells.append(f"{(p['rank'] if p['rank'] is not None else '-')!s:>10s} {p['branch'] or '-':5s}")
        ib = in_branch.get(key)
        ibs = f"{ib['rank_in_branch']}/{ib['n_branch']} {ib['branch']}" if ib else "-"
        print(f"{key:28s} " + " ".join(cells) + f"  {ibs}")
    print()
    for n in names:
        b = boards[n]
        kinds = " ".join(f"{k} {v['found']}/{v['recorded']}" for k, v in sorted(b["by_kind"].items()))
        print(f"{n}: recall@20 {b['found']}/{b['recorded']} ({kinds})")
    print()
    print("candidates per km2 above calibrated 0 / 1 / 2 (nominal 1 / 0.1 / 0.01):")
    for sid in run["strips"]:
        cells = " | ".join(
            f"{n} " + " ".join(f"{boards[n]['above'][sid][str(lv)]:8.3f}" for lv in LEVELS) for n in names
        )
        print(f"  {sid}: {cells}")
    print()
    print("split-half (fit on even tiles, applied to odd): realised per km2 above 0 / 1 / 2")
    for k, per in halves.items():
        for sid, h in per.items():
            if h:
                r = h["realised_per_km2"]
                print(
                    f"  {k} {sid}: "
                    + " ".join(f"{r[str(lv)]:8.3f}" for lv in LEVELS)
                    + f"  (n fit {h['n_fit']}, test {h['n_test']})"
                )
    print(f"\nwritten: {out / 'offline_strip_calibration.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
