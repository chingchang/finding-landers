"""The two-sided test for dark candidates, docs/plan.md item 16; the protocol is docs/proposals/darkrelief-v1-protocol.md.

    uv run scripts/darkrelief.py measure --jobs 3     the detector over the tuning strips, features on; rerun to resume
    uv run scripts/darkrelief.py tiles                the same on item 13's plantings, repeated from its seed; rerun to resume
    uv run scripts/darkrelief.py score                both boards, every arm

Writes under out/darkrelief. Item 15's populations (scripts/halfcal.py pop, redetect) are the reference the reruns must agree
with. Only tuning strips and the 46 listed tiles are read. No paid model is called.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import halfcal as hs  # noqa: E402
import rerank as rr  # noqa: E402

from landers import config, relief, shape  # noqa: E402
from landers.detect import (  # noqa: E402
    DetectorConfig,
    detect_strip_parallel,
    detect_tile,
    finish_tile,
    load_calibration,
    load_shape_rules,
)
from landers.rerank import model as rm  # noqa: E402
from landers.search import export as ex  # noqa: E402
from landers.search import run  # noqa: E402
from landers.strip import Strip  # noqa: E402

OUT = config.REPO_ROOT / "out" / "darkrelief"
FEATURES = OUT / "features"
TILES = OUT / "t10"
SHAPE_V3 = config.REPO_ROOT / "landers" / "shape_v3.json"
CALIBRATION = config.REPO_ROOT / "landers" / "calibration_v0.json"
FIELDS = (
    "relief_dipole",
    "relief_sun_min_z",
    "relief_anti_min_z",
    "relief_height_m",
    "relief_width_m",
    "two_sided",
    "shadow_height_m",
)
SCORE_TOLERANCE = 0.0021  # both sides are rounded to 0.001, one of them before a gain is added
ARMS = ("whole_fit", "p0005", "p002", "flipped", "recorded", "compact_only", "dark_only")


def frozen_config(rules: str | None) -> DetectorConfig:
    return DetectorConfig(calibration=str(CALIBRATION), shape_rules=rules, relief_features=True)


def feature_arrays(extras: list[dict]) -> dict[str, np.ndarray]:
    return {k: np.array([e.get(k, np.nan) for e in extras], np.float64) for k in FIELDS}


# ---------------------------------------------------------------- the measurement


def check_against_population(sid: str, cands: list[dict]) -> None:
    """The rerun must be frozen-v1's list, or the features belong to other candidates."""
    with np.load(hs.POP / f"{sid}.npz") as z:
        row, col, score, raw, branch = z["row"], z["col"], z["score"], z["raw"], z["branch"]
    if len(cands) != len(row):
        raise RuntimeError(f"{sid}: {len(cands)} candidates against {len(row)} in the population")
    now_row = np.array([c["row"] for c in cands])
    now_col = np.array([c["col"] for c in cands])
    now_raw = np.array([c["extra"]["raw_score"] for c in cands])
    now_score = np.array([c["score"] for c in cands])
    same = (
        np.array_equal(now_row, row)
        and np.array_equal(now_col, col)
        and np.array_equal(now_raw, raw)
        and np.array_equal(np.array([c["branch"] for c in cands]), branch)
    )
    if not same or np.abs(now_score - score).max() > SCORE_TOLERANCE:
        raise RuntimeError(f"{sid}: the rerun differs from frozen-v1's list")


def measure(a) -> int:
    sites, _, _ = rr.controls()
    FEATURES.mkdir(parents=True, exist_ok=True)
    rules = shape.ShapeRules.load(SHAPE_V3)
    first_group = set(
        rr.load(hs.LISTS[0][0])["strips"]
    )  # scored without rules in the run, the rules applied afterwards
    tuning = sorted(hs.tuning_strips(sites))
    for sid in tuning:
        out = FEATURES / f"{sid}.npz"
        if out.exists():
            continue
        ex.refuse_blind(sites, sid)
        t0 = time.time()
        cfg = frozen_config(None if sid in first_group else str(SHAPE_V3))
        strip = Strip.open(sid)
        cands = detect_strip_parallel(strip, cfg, a.jobs)["candidates"]
        if sid in first_group:
            cands = [shape.apply_rules_json(c, rules) for c in cands]
        check_against_population(sid, cands)
        rr.save_npz(out, **feature_arrays([c["extra"] for c in cands]))
        print(f"{sid}: {len(cands)} candidates agree, {time.time() - t0:.0f}s", flush=True)
    missing = [sid for sid in tuning if not (FEATURES / f"{sid}.npz").exists()]
    print(f"missing: {missing}")
    return 1 if missing else 0


def tiles(a) -> int:
    sites, _, _ = rr.controls()
    meta = rr.load(rr.EXPORT / "pieces.json")
    listed = hs.listed_tiles()
    cuts, _ = rr.build_cuts(meta, sites)
    per_tile, _ = rr.allocate(cuts, listed)
    cfg = rr.tp.TransplantConfig(**meta["config"])
    dcfg = frozen_config(str(SHAPE_V3))
    cal, rules = load_calibration(dcfg), load_shape_rules(dcfg)
    TILES.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for i, t in enumerate(listed):
        out = TILES / f"{t['file'][:-4]}.npz"
        if out.exists():
            continue
        rec = rr.load(hs.TILES / f"{t['file'][:-4]}.json")
        win = ex.read_window(rr.EXPORT / "tiles" / t["file"])
        rng = np.random.default_rng([rr.SEED, i])
        idxs = list(per_tile[rr.tile_key(t)])
        rng.shuffle(idxs)
        planted, _ = rr.tp.place_in_tile(win, rr.label_of(t["strip"]), cuts, idxs, rng, cfg, rr.tile_key(t))
        found = finish_tile(detect_tile(planted, rr.label_of(t["strip"]), dcfg), dcfg, cal, rules)
        now = [(round(c.row - t["row0"], 1), round(c.col - t["col0"], 1), round(c.score, 4), c.branch) for c in found]
        if now != [(d["row"], d["col"], d["score"], d["branch"]) for d in rec]:
            raise RuntimeError(f"{t['file']}: the rerun differs from item 13's record")
        rr.save_npz(out, **feature_arrays([c.extra for c in found]))
        print(f"{t['file']}: {len(now)} detections agree, {time.time() - t0:.0f}s", flush=True)
    print("all tiles agree with item 13's records")
    return 0


# ---------------------------------------------------------------- the arms


class Pop:
    """The dark candidates' test values on one list, aligned with the list."""

    def __init__(self, branch: np.ndarray, f: dict[str, np.ndarray]):
        self.branch = branch
        self.is_ = {b: branch == b for b in relief.BRANCHES}
        self.primary = relief.test_value(f)
        self.flipped = relief.test_value(f, flipped=True)
        self.recorded = relief.recorded_value(f)
        self.dipole = f["relief_dipole"]


def values_of(p: Pop, kind: str) -> np.ndarray:
    return {"primary": p.primary, "flipped": p.flipped, "recorded": p.recorded}[kind]


def fit(pops: list[Pop], kind: str, target: float, branches=relief.BRANCHES) -> dict:
    out = {}
    for b in branches:
        out[b] = relief.fit_rule(np.concatenate([values_of(p, kind)[p.is_[b]] for p in pops]), target)
    return out


def gain_of(p: Pop, kind: str, rules: dict) -> np.ndarray:
    g = np.zeros(len(p.branch))
    for b, r in rules.items():
        g[p.is_[b]] = relief.gains(values_of(p, kind)[p.is_[b]], r)
    return g


def arm_rules(pops: list[Pop]) -> dict:
    return {
        "whole_fit": ("primary", fit(pops, "primary", relief.P_TARGET)),
        "p0005": ("primary", fit(pops, "primary", 0.0005)),
        "p002": ("primary", fit(pops, "primary", 0.002)),
        "flipped": ("flipped", fit(pops, "flipped", relief.P_TARGET)),
        "recorded": ("recorded", fit(pops, "recorded", relief.P_TARGET)),
        "compact_only": ("primary", fit(pops, "primary", relief.P_TARGET, ("dark_compact",))),
        "dark_only": ("primary", fit(pops, "primary", relief.P_TARGET, ("dark",))),
    }


def rules_json(rules: dict) -> dict:
    return {b: (r.to_json() if r else None) for b, r in rules.items()}


# ---------------------------------------------------------------- the boards


def sham_hits(dets: list[dict], values: np.ndarray, shams: list[dict], allowed: int, truths: list[dict]) -> int:
    """Sham plantings with a detection above the score at which ``allowed`` false alarms are reached. Sham detections count
    as false alarms there, as on the board."""
    by_tile: dict = {}
    for t in truths:
        by_tile.setdefault(t["tile"], []).append(t)
    order = np.argsort(-values, kind="stable")
    n_fa, threshold = 0, -np.inf
    for i in order:
        d = dets[i]
        if not any(
            np.hypot(d["row"] - t["row"], d["col"] - t["col"]) <= t["radius_px"] for t in by_tile.get(d["tile"], [])
        ):
            n_fa += 1
            if n_fa > allowed:
                threshold = float(values[i])
                break
    hit = 0
    for s in shams:
        for d, v in zip(dets, values, strict=True):
            if (
                v > threshold
                and d["tile"] == s["tile"]
                and np.hypot(d["row"] - s["row"], d["col"] - s["col"]) <= s["radius_px"]
            ):
                hit += 1
                break
    return hit


def score_all(a) -> int:
    sites, thresholds, answers = rr.controls()
    tuning = sorted(hs.tuning_strips(sites))
    for sid in tuning:
        ex.refuse_blind(sites, sid)
    pieces = rr.tp.key_pieces(answers, thresholds, rr.tp.tuning_sources(sites))
    piece_strips = sorted({p["strip"] for p in pieces})
    site_of = {sid: s["name"] for s in sites["sites"] if s["group"] == "tuning" for sid in s["strips"]}
    t0 = time.time()

    lists: dict = {}
    pops: dict[str, Pop] = {}
    for sid in tuning:
        with np.load(hs.POP / f"{sid}.npz") as z:
            lists[sid] = {k: z[k] for k in ("row", "col", "score", "branch")}
        with np.load(FEATURES / f"{sid}.npz") as z:
            pops[sid] = Pop(lists[sid]["branch"], {k: z[k] for k in FIELDS})

    def rows(sid: str, values: np.ndarray) -> list[dict]:
        s = lists[sid]
        return [
            {"row": float(r), "col": float(c), "score": float(v), "branch": str(b)}
            for r, c, v, b in zip(s["row"], s["col"], values, s["branch"], strict=True)
        ]

    # the transplant board, the detections aligned with their features
    dets, truths = hs.board_tiles(thresholds)
    tile_files = {rr.tile_key(t): t["file"][:-4] for t in hs.listed_tiles()}
    keys = list(dict.fromkeys(d["tile"] for d in dets))
    parts = []
    for key in keys:
        with np.load(TILES / f"{tile_files[key]}.npz") as z:
            parts.append({k: z[k] for k in FIELDS})
    tile_f = {k: np.concatenate([p[k] for p in parts]) for k in FIELDS}
    n_by_tile = [len(p[FIELDS[0]]) for p in parts]
    if [d["tile"] for d in dets] != [k for k, n in zip(keys, n_by_tile, strict=True) for _ in range(n)]:
        raise RuntimeError("the tile features do not line up with the detections")
    tile_pop = Pop(np.array([d["branch"] for d in dets]), tile_f)
    frozen_tile = np.array([d["score"] for d in dets])

    targets = hs.target_strips()
    area = float(rr.load(rr.RUN / "run.json")["area_km2"])
    median_km2 = statistics.median(rr.target_areas(targets).values())
    rates = [(f"N{n}", n / median_km2) for n in rr.TOP_NS] + [
        ("board_rate", float(thresholds["pass"]["max_false_alarms_per_km2"]))
    ]
    no_texture = set(a.no_texture)

    def scored(values: np.ndarray) -> dict:
        ds = [{**d, "score": float(v)} for d, v in zip(dets, values, strict=True)]
        return {name: rr.summarise(rr.transplant_rows(ds, truths, area, fa, no_texture)) for name, fa in rates}

    # frozen-v1 must be item 13's on both boards
    frozen_key = rr.key_ranks({sid: rows(sid, lists[sid]["score"]) for sid in piece_strips}, answers, thresholds)
    frozen_board = scored(frozen_tile)
    ref = rr.load(hs.FROZEN_REFERENCE)["frozen_v1"]
    key_curve = rr.curve(frozen_key.values())
    board_curve = {k: v["found"] for k, v in frozen_board.items()}
    if key_curve != ref["key_curve"] or board_curve != {k: v["found"] for k, v in ref["transplant"].items()}:
        print(f"frozen-v1 differs from item 13's: {key_curve}, {board_curve}", file=sys.stderr)
        return 2
    print(f"frozen-v1 agrees, {time.time() - t0:.0f}s", flush=True)

    all_pops = [pops[sid] for sid in tuning]

    def one_arm(ranks: dict, board: dict) -> dict:
        k = rr.curve(ranks.values())
        by_site = rr.site_curve(ranks)
        out = {
            "key_curve": k,
            "key_n": len(ranks),
            "key_interval_95_at_20": rm.wilson(k["20"], len(ranks)),
            "key_kinds": rr.kind_curve(ranks, pieces),
            "key_by_site": by_site,
            "key_spread_at_20": rr.spread(by_site),
            "key_ranks": ranks,
            "transplant": board,
            "transplant_curve": {n: v["found"] for n, v in board.items()},
            "transplant_spread_at_20": rr.spread(board["N20"]["by_site"]),
            "dropped_from_top_20": sorted(
                x
                for x, v in frozen_key.items()
                if v is not None and v <= rr.PRIMARY_N and not (ranks.get(x) is not None and ranks[x] <= rr.PRIMARY_N)
            ),
        }
        out["key_beats"] = k["20"] > key_curve["20"]
        out["transplant_beats"] = board["N20"]["found"] > frozen_board["N20"]["found"]
        return out

    arms: dict = {"frozen_v1": one_arm(frozen_key, frozen_board)}
    arms["frozen_v1"]["key_beats"] = arms["frozen_v1"]["transplant_beats"] = False

    # the folds: each site's pieces and plantings judged by rules fitted on the other sites' strips
    names = sorted({p["site"] for p in pieces})
    folds, loso_ranks = {}, {}
    loso_board: dict = {n: {"n": 0, "found": 0, "by_kind": {}, "by_site": {}, "by_ground": {}} for n, _ in rates}
    for site in names:
        others = [pops[sid] for sid in tuning if site_of[sid] != site]
        rules = fit(others, "primary", relief.P_TARGET)
        folds[site] = rules_json(rules)
        here = {
            sid: rows(sid, lists[sid]["score"] + gain_of(pops[sid], "primary", rules))
            for sid in piece_strips
            if site_of[sid] == site
        }
        loso_ranks.update(
            rr.key_ranks(here, {**answers, "sites": [s for s in answers["sites"] if s["name"] == site]}, thresholds)
        )
        ds = [
            {**d, "score": float(v)}
            for d, v in zip(dets, frozen_tile + gain_of(tile_pop, "primary", rules), strict=True)
        ]
        for name, fa in rates:
            for x in rr.transplant_rows(ds, truths, area, fa, no_texture):
                if x["site"] != site:
                    continue
                b = loso_board[name]
                b["n"] += x["n"]
                b["found"] += x["found"]
                for group, value in (("kind", x["kind"]), ("site", x["site"]), ("ground", x["ground"])):
                    d = b[f"by_{group}"].setdefault(value, {"n": 0, "found": 0})
                    d["n"] += x["n"]
                    d["found"] += x["found"]
        print(f"fold {site}, {time.time() - t0:.0f}s", flush=True)
    for b in loso_board.values():
        b["interval_95"] = rm.wilson(b["found"], b["n"])
    if {k: v for k, v in sorted(loso_ranks.items())}.keys() != {k: v for k, v in sorted(frozen_key.items())}.keys():
        raise RuntimeError("the folds did not cover the key")
    arms["primary_loso"] = one_arm(loso_ranks, loso_board)

    fitted = arm_rules(all_pops)
    allowed = int(dict(rates)["N20"] * area)
    shams = sham_rows(thresholds)
    sham = {"frozen_v1": sham_hits(dets, frozen_tile, shams, allowed, truths), "n": len(shams)}
    for arm in ARMS:
        kind, rules = fitted[arm]
        lists_now = {sid: rows(sid, lists[sid]["score"] + gain_of(pops[sid], kind, rules)) for sid in piece_strips}
        values = frozen_tile + gain_of(tile_pop, kind, rules)
        arms[arm] = {
            **one_arm(rr.key_ranks(lists_now, answers, thresholds), scored(values)),
            "rules": rules_json(rules),
        }
        if arm == "whole_fit":
            sham["whole_fit"] = sham_hits(dets, values, shams, allowed, truths)
        print(f"{arm}, {time.time() - t0:.0f}s", flush=True)

    # how each piece's own dark candidates read, under the whole fit, for the report and the person's eye
    whole = fitted["whole_fit"][1]
    per_strip = {}
    for sid in tuning:
        p = pops[sid]
        g = gain_of(p, "primary", whole)
        row: dict = {"site": site_of[sid]}
        for b in relief.BRANCHES:
            m = p.is_[b]
            pos, neg = int((p.dipole[m] > 0).sum()), int((p.dipole[m] < 0).sum())
            row[b] = {
                "n": int(m.sum()),
                "passing": int((g[m] > 0).sum()),
                "fraction": round(float((g[m] > 0).mean()), 5) if m.any() else None,
                "dipole_positive": pos,
                "dipole_negative": neg,
                "measured": int(np.isfinite(p.dipole[m]).sum()),
            }
        per_strip[sid] = row

    p = arms["primary_loso"]
    rule = {
        "key_beats": p["key_beats"],
        "transplant_beats": p["transplant_beats"],
        "no_piece_dropped": not p["dropped_from_top_20"],
    }
    rule["met"] = bool(all(rule.values()))
    res = {
        "protocol": "docs/proposals/darkrelief-v1-protocol.md",
        "git": run.git_state(),
        "not_blind": "every number here is on tuning sites; perseverance, insight, zhurong and beagle2 were sealed for frozen-v1 and are not blind",
        "rule": rule,
        "planted_km2": area,
        "median_target_km2": median_km2,
        "rates_per_km2": dict(rates),
        "false_alarms_allowed": {name: int(fa * area) for name, fa in rates},
        "no_texture": sorted(no_texture),
        "arms": arms,
        "folds": folds,
        "per_strip": per_strip,
        "piece_candidates": piece_candidates(pieces, lists, pops, whole, thresholds),
        "sham_at_N20": sham,
        "seconds": round(time.time() - t0),
    }
    rr.write_json(OUT / "results.json", res)
    for arm, v in arms.items():
        print(
            f"{arm}: key {v['key_curve']} transplant {v['transplant_curve']} dropped {v['dropped_from_top_20']}",
            flush=True,
        )
    print(f"sham {sham}; rule {rule}; written {OUT / 'results.json'}")
    return 0


def sham_rows(thresholds: dict) -> list[dict]:
    cuts = rr.load(rr.RUN / "run.json")["cuts"]
    out = []
    for t in hs.listed_tiles():
        for p in rr.load(rr.RUN / "tiles" / f"{t['file'][:-4]}.json")["placements"]:
            if p["sham"]:
                cut = cuts[p["cut_index"]]
                out.append(
                    {
                        "tile": p["tile"],
                        "row": p["row"],
                        "col": p["col"],
                        "radius_px": hs.match_radius_px(thresholds, cut["scale_m"], p["kind"]),
                    }
                )
    return out


def piece_candidates(pieces: list[dict], lists: dict, pops: dict, whole: dict, thresholds: dict) -> list[dict]:
    """Every dark candidate within a piece's match radius: its measured values, whether it passes, and its frozen score."""
    out = []
    for piece in pieces:
        sid = piece["strip"]
        s, p = lists[sid], pops[sid]
        radius = hs.match_radius_px(thresholds, rr.label_of(sid).scale_m, piece["kind"])
        near = np.flatnonzero(np.hypot(s["row"] - piece["row"], s["col"] - piece["col"]) <= radius)
        g = gain_of(p, "primary", whole)
        for i in near:
            b = str(s["branch"][i])
            if b in relief.BRANCHES:
                out.append(
                    {
                        "piece": f"{piece['site']}/{piece['piece']}/{sid}",
                        "kind": piece["kind"],
                        "branch": b,
                        "frozen_score": round(float(s["score"][i]), 3),
                        "value": None if not np.isfinite(p.dipole[i]) else round(float(p.dipole[i]), 2),
                        "passes_fixed": bool(np.isfinite(p.primary[i])),
                        "gain": round(float(g[i]), 3),
                    }
                )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--jobs", type=int, default=3)
    sub.add_parser("tiles")
    f = sub.add_parser("score")
    f.add_argument("--no-texture", nargs="*", default=[], help="target strips with no ground texture, reported apart")
    a = ap.parse_args(argv)
    return {"measure": measure, "tiles": tiles, "score": score_all}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
