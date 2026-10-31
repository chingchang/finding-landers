"""Per-strip calibration with an honest tail, docs/plan.md item 15; the protocol is docs/proposals/halfcal-v1-protocol.md.

    uv run scripts/halfcal.py pop                     raw scores of the frozen-v1 lists, strip by strip; rerun to resume
    uv run scripts/halfcal.py redetect                the detector on item 13's saved planted tiles; rerun to resume
    uv run scripts/halfcal.py score                   both boards, every arm, and the check on the other half
    uv run scripts/halfcal.py column LIST.json ...    a copy of each list with the half-fitted rate beside each score
                                                      (item 15a; the order and every other field stay); rerun to resume

Writes under out/halfcal. A strip of a site that is not a tuning site, other than a listed target strip, is refused; column
refuses a strip of a blind site. No paid model is called.
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
import rerank as rr  # noqa: E402

from landers import config, shape  # noqa: E402
from landers import halfcal as hc  # noqa: E402
from landers.calibrate import fit_scores  # noqa: E402
from landers.detect import DetectorConfig, detect_tile, finish_tile, load_calibration, load_shape_rules  # noqa: E402
from landers.rerank import model as rm  # noqa: E402
from landers.score import match_radius_px  # noqa: E402
from landers.search import export as ex  # noqa: E402
from landers.search import run  # noqa: E402

OUT = config.REPO_ROOT / "out" / "halfcal"
POP = OUT / "pop"
TILES = OUT / "t10"
SEARCH = config.REPO_ROOT / "out" / "search" / "candidates"
FROZEN_REFERENCE = config.REPO_ROOT / "docs" / "reports" / "2026-10-30-reranker" / "summary.json"
LISTS = (  # the frozen-v1 lists of the tuning strips, as the export took them
    (
        config.REPO_ROOT / "out" / "shape_v3" / "candidates_v03_features.json",
        config.REPO_ROOT / "landers" / "shape_v3.json",
    ),
    (config.REPO_ROOT / "out" / "heldout_v1" / "candidates_heldout_v1.json", None),
    (config.REPO_ROOT / "out" / "heldout_v1" / "candidates_final_exam_v1.json", None),
)
LEVELS = (0.0, 0.5, 1.0, 1.5, 2.0)
SHIFT_M = 500.0
ARMS = ("primary", "shift", "whole_strip", "extrapolated", "no_rules", "better_rank")


def tuning_strips(sites: dict) -> set[str]:
    return {sid for s in sites["sites"] if s["group"] == "tuning" for sid in s["strips"]}


def listed_tiles() -> list[dict]:
    return rr.load(rr.EXPORT / "tiles.json")["tiles"]


def target_strips() -> list[str]:
    return sorted({t["strip"] for t in listed_tiles()})


def save_population(sid: str, cands: list[dict], rules=None) -> None:
    rows, cols, score, gain, raw, branch = [], [], [], [], [], []
    for c in cands:
        if rules is not None:
            c = shape.apply_rules_json(c, rules)
        x = c.get("extra") or {}
        if "raw_score" not in x:
            raise ValueError(f"{sid}: a candidate has no raw score")
        rows.append(c["row"])
        cols.append(c["col"])
        score.append(c["score"])
        gain.append(x.get("shape_gain", 0.0))
        raw.append(x["raw_score"])
        branch.append(c["branch"])
    rr.save_npz(
        POP / f"{sid}.npz",
        row=np.array(rows, np.float64),
        col=np.array(cols, np.float64),
        score=np.array(score, np.float64),
        gain=np.array(gain, np.float64),
        raw=np.array(raw, np.float64),
        branch=np.array(branch),
    )
    print(f"{sid}: {len(rows)} candidates", flush=True)


def population(a) -> int:
    sites, _, _ = rr.controls()
    tuning = tuning_strips(sites)
    for path, rules_path in LISTS:
        wanted = {sid for sid in tuning if not (POP / f"{sid}.npz").exists()}
        if not wanted:
            break
        rules = shape.ShapeRules.load(rules_path) if rules_path else None
        d = rr.load(path)
        for sid, entry in d["strips"].items():
            if sid in wanted:
                save_population(sid, entry["candidates"], rules)
        del d
    for sid in target_strips():
        ex.refuse_blind(sites, sid)
        if not (POP / f"{sid}.npz").exists():
            save_population(sid, rr.load(run.strip_output(SEARCH, sid))["strips"][sid]["candidates"])
    missing = sorted(sid for sid in tuning | set(target_strips()) if not (POP / f"{sid}.npz").exists())
    print(f"missing: {missing}")
    return 1 if missing else 0


def redetect(a) -> int:
    """Item 13's plantings repeated from its seed, and the detector on them. Item 13's records hold no raw scores, and its
    saved tiles are rounded to whole samples while it detected on the unrounded planting, so the plant is repeated in
    memory. Placements and detections must agree with the records, or the board would not be the same board."""
    sites, _, _ = rr.controls()
    meta = rr.load(rr.EXPORT / "pieces.json")
    tiles = listed_tiles()
    cuts, _ = rr.build_cuts(meta, sites)
    per_tile, _ = rr.allocate(cuts, tiles)
    cfg = rr.tp.TransplantConfig(**meta["config"])
    dcfg = DetectorConfig(
        calibration=str(config.REPO_ROOT / "landers/calibration_v0.json"),
        shape_rules=str(config.REPO_ROOT / "landers/shape_v3.json"),
    )
    cal, rules = load_calibration(dcfg), load_shape_rules(dcfg)
    TILES.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for i, t in enumerate(tiles):
        out = TILES / f"{t['file'][:-4]}.json"
        if out.exists():
            continue
        rec = rr.load(rr.RUN / "tiles" / f"{t['file'][:-4]}.json")
        win = ex.read_window(rr.EXPORT / "tiles" / t["file"])
        rng = np.random.default_rng([rr.SEED, i])
        idxs = list(per_tile[rr.tile_key(t)])
        rng.shuffle(idxs)
        planted, placed = rr.tp.place_in_tile(win, rr.label_of(t["strip"]), cuts, idxs, rng, cfg, rr.tile_key(t))
        if [p.to_json() for p in placed] != rec["placements"]:
            raise RuntimeError(f"{t['file']}: the placements differ from item 13's record")
        cands = finish_tile(detect_tile(planted, rr.label_of(t["strip"]), dcfg), dcfg, cal, rules)
        now = [
            {
                "row": round(c.row - t["row0"], 1),
                "col": round(c.col - t["col0"], 1),
                "score": round(c.score, 4),
                "branch": c.branch,
            }
            for c in cands
        ]
        was = [{k: d[k] for k in ("row", "col", "score", "branch")} for d in rec["detections"]]
        if now != was:
            raise RuntimeError(f"{t['file']}: the rerun differs from item 13's record")
        rr.write_json(
            out,
            [
                {**x, "raw": c.extra["raw_score"], "gain": c.extra.get("shape_gain", 0.0)}
                for x, c in zip(now, cands, strict=True)
            ],
        )
        print(f"{t['file']}: {len(now)} detections agree, {time.time() - t0:.0f}s", flush=True)
    print("all tiles agree with item 13's records")
    return 0


# ---------------------------------------------------------------- one strip's arms


class Strip:
    """A strip's population, the valid area of each colour under both splits, and its fitted curves."""

    def __init__(self, sid: str):
        self.sid = sid
        with np.load(POP / f"{sid}.npz") as z:
            self.row, self.col, self.score, self.gain, self.raw = z["row"], z["col"], z["score"], z["gain"], z["raw"]
            self.branch = z["branch"]
        self.table = self.score - self.gain
        es = ex.ExportedStrip(rr.EXPORT, sid)
        self.scale = es.label.scale_m
        valid, step = es.overview.valid, es.overview_step
        self.area = {s: hc.colour_areas(valid, step, self.scale, s) for s in (0.0, SHIFT_M)}
        self.total = sum(self.area[0.0])
        self.cals = {
            s: hc.cross_fit(self.branch, self.raw, hc.colour(self.row, self.col, self.scale, s), self.area[s])
            for s in self.area
        }
        self.whole = hc.fit_population(self.branch, self.raw, self.total)
        by_branch = {str(b): self.raw[self.branch == b].tolist() for b in np.unique(self.branch)}
        self.extrap = fit_scores(by_branch, self.total, "item8_tail", top_exclude=20)

    def half(self, q: dict, shift: float = 0.0) -> np.ndarray:
        return hc.score_by_other(
            self.cals[shift], q["branch"], q["raw"], q["table"], hc.colour(q["row"], q["col"], self.scale, shift)
        )

    def arm(self, name: str, q: dict) -> np.ndarray:
        """Each arm's score of the candidates in ``q``, rule gains added except for ``no_rules``."""
        if name == "primary":
            return self.half(q) + q["gain"]
        if name == "shift":
            return self.half(q, SHIFT_M) + q["gain"]
        if name == "whole_strip":
            return hc.capped_scores(self.whole, q["branch"], q["raw"], q["table"]) + q["gain"]
        if name == "extrapolated":
            return (
                np.array([self.extrap.calibrated(str(b), float(r)) for b, r in zip(q["branch"], q["raw"], strict=True)])
                + q["gain"]
            )
        if name == "no_rules":
            return self.half(q)
        raise ValueError(name)

    def query(self) -> dict:
        return {
            "row": self.row,
            "col": self.col,
            "branch": self.branch,
            "raw": self.raw,
            "table": self.table,
            "gain": self.gain,
        }


def fused(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """The better of two ranks, as experiments/rerank_fusion.py. Both inputs and the output: higher is better."""

    def rank(x):
        r = np.zeros(len(x))
        r[np.argsort(-x, kind="stable")] = np.arange(1, len(x) + 1)
        return r

    a, b = rank(first), rank(second)
    return -(np.minimum(a, b) + np.maximum(a, b) / (2.0 * len(a) + 1))


# ---------------------------------------------------------------- the boards


def key_board(strips: dict[str, Strip], piece_strips: list[str], answers: dict, thresholds: dict) -> dict:
    def rows(s: Strip, values: np.ndarray) -> list[dict]:
        return [
            {"row": float(r), "col": float(c), "score": float(v), "branch": str(b)}
            for r, c, v, b in zip(s.row, s.col, values, s.branch, strict=True)
        ]

    out = {
        "frozen_v1": rr.key_ranks(
            {sid: rows(strips[sid], strips[sid].score) for sid in piece_strips}, answers, thresholds
        )
    }
    for arm in ARMS:
        lists = {}
        for sid in piece_strips:
            s = strips[sid]
            v = fused(s.score, s.arm("primary", s.query())) if arm == "better_rank" else s.arm(arm, s.query())
            lists[sid] = rows(s, v)
        out[arm] = rr.key_ranks(lists, answers, thresholds)
    return out


def board_tiles(thresholds: dict) -> tuple[list[dict], list[dict]]:
    cuts = rr.load(rr.RUN / "run.json")["cuts"]
    dets, truths = [], []
    for t in listed_tiles():
        key = rr.tile_key(t)
        for d in rr.load(TILES / f"{t['file'][:-4]}.json"):
            dets.append(
                {
                    **d,
                    "tile": key,
                    "strip": t["strip"],
                    "row_abs": d["row"] + t["row0"],
                    "col_abs": d["col"] + t["col0"],
                }
            )
        for p in rr.load(rr.RUN / "tiles" / f"{t['file'][:-4]}.json")["placements"]:
            if not p["sham"]:
                cut = cuts[p["cut_index"]]
                truths.append(
                    {
                        "tile": p["tile"],
                        "row": p["row"],
                        "col": p["col"],
                        "kind": p["kind"],
                        "site": p["site"],
                        "piece": p["piece"],
                        "size_m": cut["size_m"],
                        "radius_px": match_radius_px(thresholds, cut["scale_m"], p["kind"]),
                        "target": t["strip"],
                    }
                )
    return dets, truths


def transplant_board(
    strips: dict[str, Strip], dets: list[dict], truths: list[dict], area: float, rates: list, no_texture: set[str]
) -> dict:
    by_strip: dict[str, list[int]] = {}
    for i, d in enumerate(dets):
        by_strip.setdefault(d["strip"], []).append(i)

    def scored(values) -> dict:
        ds = [{**d, "score": float(v)} for d, v in zip(dets, values, strict=True)]
        return {name: rr.summarise(rr.transplant_rows(ds, truths, area, fa, no_texture)) for name, fa in rates}

    frozen = np.array([d["score"] for d in dets])
    out = {"frozen_v1": scored(frozen)}
    primary = None
    for arm in ("primary", "shift", "whole_strip", "extrapolated", "no_rules"):
        values = np.zeros(len(dets))
        for sid, idx in by_strip.items():
            sel = [dets[i] for i in idx]
            raw = np.array([x["raw"] for x in sel])
            gain = np.array([x["gain"] for x in sel])
            q = {
                "row": np.array([x["row_abs"] for x in sel]),
                "col": np.array([x["col_abs"] for x in sel]),
                "branch": np.array([x["branch"] for x in sel]),
                "raw": raw,
                "table": np.array([x["score"] for x in sel]) - gain,
                "gain": gain,
            }
            values[idx] = strips[sid].arm(arm, q)
        out[arm] = scored(values)
        if arm == "primary":
            primary = values
    out["better_rank"] = scored(fused(frozen, primary))
    return out


# ---------------------------------------------------------------- the check on the other half


def rate_rows(strips: dict[str, Strip], sids: list[str]) -> dict:
    per: dict = {}
    for sid in sids:
        s = strips[sid]
        q = s.query()
        caps = [hc.cap_of(x) for x in s.area[0.0]]
        arms = {
            "halves": (s.half(q), min(caps)),
            "table_frozen_v1": (s.table, None),
            "extrapolated": (s.arm("extrapolated", {**q, "gain": np.zeros(len(s.raw))}), None),
        }
        n_b = len(np.unique(s.branch))
        for arm, (values, cap) in arms.items():
            r = hc.realised_rates(values, s.branch, s.total, LEVELS, cap)
            for lv, d in r.items():
                nominal = 10.0**-lv
                ratio_b = [v / nominal for v in d["branches"].values()]
                per.setdefault(arm, {}).setdefault(str(lv), []).append(
                    {
                        "strip": sid,
                        "all_per_km2": round(d["all"], 4),
                        "ratio_all": round(d["all"] / (n_b * nominal), 3),
                        "ratio_branch_median": round(statistics.median(ratio_b), 3),
                        "n": d["n"],
                    }
                )
    out: dict = {}
    for arm, levels in per.items():
        out[arm] = {}
        for lv, rows in levels.items():
            ratios = [x["ratio_all"] for x in rows]
            med_b = [x["ratio_branch_median"] for x in rows]
            out[arm][lv] = {
                "strips": len(rows),
                "ratio_all_min": min(ratios),
                "ratio_all_median": round(statistics.median(ratios), 3),
                "ratio_all_max": max(ratios),
                "ratio_branch_median_min": min(med_b),
                "ratio_branch_median_max": max(med_b),
                "rows": rows,
            }
    return out


def top_branches(branches: np.ndarray, values: np.ndarray) -> dict[str, int]:
    names, counts = np.unique(branches[np.argsort(-values, kind="stable")[:20]], return_counts=True)
    return {str(a): int(b) for a, b in zip(names, counts, strict=True)}


def top20_makeup(strips: dict[str, Strip], piece_strips: list[str]) -> dict:
    out = {}
    for sid in piece_strips:
        s = strips[sid]
        half = s.half(s.query())
        primary = half + s.gain
        cap = min(hc.cap_of(x) for x in s.area[0.0])
        top = np.argsort(-primary, kind="stable")[:20]
        out[sid] = {
            "frozen_v1": top_branches(s.branch, s.score),
            "primary": top_branches(s.branch, primary),
            "at_cap_in_primary_top_20": int((half[top] >= cap).sum()),
            "at_cap_in_strip": int((half >= cap).sum()),
            "candidates": len(s.raw),
            "area_km2": round(s.total, 2),
            "cap": round(cap, 3),
        }
    return out


def score_all(a) -> int:
    sites, thresholds, answers = rr.controls()
    tuning = sorted(tuning_strips(sites))
    targets = target_strips()
    for sid in tuning + targets:
        ex.refuse_blind(sites, sid)
    t0 = time.time()
    strips = {sid: Strip(sid) for sid in tuning + targets}
    print(f"{len(strips)} strips fitted, {time.time() - t0:.0f}s", flush=True)
    pieces = rr.tp.key_pieces(answers, thresholds, rr.tp.tuning_sources(sites))
    piece_strips = sorted({p["strip"] for p in pieces})
    key = key_board(strips, piece_strips, answers, thresholds)
    print(f"key board, {time.time() - t0:.0f}s", flush=True)

    dets, truths = board_tiles(thresholds)
    area = float(rr.load(rr.RUN / "run.json")["area_km2"])
    median_km2 = statistics.median(rr.target_areas(targets).values())
    rates = [(f"N{n}", n / median_km2) for n in rr.TOP_NS] + [
        ("board_rate", float(thresholds["pass"]["max_false_alarms_per_km2"]))
    ]
    board = transplant_board(strips, dets, truths, area, rates, set(a.no_texture))
    print(f"transplant board, {time.time() - t0:.0f}s", flush=True)

    ref = rr.load(FROZEN_REFERENCE)["frozen_v1"]
    key_frozen = rr.curve(key["frozen_v1"].values())
    tp_frozen = {k: v["found"] for k, v in board["frozen_v1"].items()}
    ref_tp = {k: v["found"] for k, v in ref["transplant"].items()}
    if key_frozen != ref["key_curve"] or tp_frozen != ref_tp:
        print(
            f"frozen-v1 differs from item 13's: key {key_frozen} against {ref['key_curve']}, transplant {tp_frozen} against {ref_tp}",
            file=sys.stderr,
        )
        return 2

    at = str(rr.PRIMARY_N)
    arms = {}
    for arm in ("frozen_v1", *ARMS):
        ranks = key[arm]
        k_curve = rr.curve(ranks.values())
        by_site = rr.site_curve(ranks)
        arms[arm] = {
            "key_curve": k_curve,
            "key_n": len(ranks),
            "key_interval_95_at_20": rm.wilson(k_curve[at], len(ranks)),
            "key_kinds": rr.kind_curve(ranks, pieces),
            "key_by_site": by_site,
            "key_spread_at_20": rr.spread(by_site),
            "key_ranks": ranks,
            "transplant": board[arm],
            "transplant_curve": {k: v["found"] for k, v in board[arm].items()},
            "transplant_spread_at_20": rr.spread(board[arm][f"N{at}"]["by_site"]),
        }
        if arm != "frozen_v1":
            arms[arm]["dropped_from_top_20"] = sorted(
                k
                for k, v in key["frozen_v1"].items()
                if v is not None and v <= rr.PRIMARY_N and not (ranks.get(k) is not None and ranks[k] <= rr.PRIMARY_N)
            )
            arms[arm]["key_beats"] = k_curve[at] > key_frozen[at]
            arms[arm]["transplant_beats"] = board[arm][f"N{at}"]["found"] > board["frozen_v1"][f"N{at}"]["found"]
    p = arms["primary"]
    rule = {
        "key_beats": p["key_beats"],
        "transplant_beats": p["transplant_beats"],
        "no_piece_dropped": not p["dropped_from_top_20"],
    }
    rule["met"] = bool(all(rule.values()))
    res = {
        "protocol": "docs/proposals/halfcal-v1-protocol.md",
        "git": run.git_state(),
        "not_blind": "every number here is on tuning sites; perseverance, insight, zhurong and beagle2 were sealed for frozen-v1 and are not blind",
        "rule": rule,
        "planted_km2": area,
        "median_target_km2": median_km2,
        "rates_per_km2": dict(rates),
        "no_texture": sorted(a.no_texture),
        "false_alarms_allowed": {name: int(fa * area) for name, fa in rates},
        "arms": arms,
        "check": {"tuning": rate_rows(strips, tuning), "targets": rate_rows(strips, targets)},
        "top20_makeup": top20_makeup(strips, piece_strips),
        "seconds": round(time.time() - t0),
    }
    rr.write_json(OUT / "results.json", res)
    for arm in ("frozen_v1", *ARMS):
        print(
            f"{arm}: key {arms[arm]['key_curve']} transplant {arms[arm]['transplant_curve']} dropped {arms[arm].get('dropped_from_top_20')}",
            flush=True,
        )
    print(f"rule {rule}; written {OUT / 'results.json'}")
    return 0


def raws_of(s: Strip, candidates: list[dict]) -> np.ndarray:
    """Each row's raw score, joined on position and branch to the strip's whole population: a list such as item 14's holds
    only the top of a strip and no raw scores, and a curve fitted on the top alone would claim the wrong rates."""
    raw_at: dict[tuple, float] = {}
    for key in zip(s.row.tolist(), s.col.tolist(), s.branch.tolist(), s.raw.tolist(), strict=True):
        if raw_at.setdefault(key[:3], key[3]) != key[3]:
            raise ValueError(f"{s.sid}: two raw scores at one position and branch")
    return np.array([raw_at[(c["row"], c["col"], c["branch"])] for c in candidates], np.float64)


def strip_column(sid: str, entry: dict, reference: dict) -> tuple[list[dict], dict]:
    """One strip's rows with the column, and its record. The whole-population count at the cap must equal item 15's."""
    if not (POP / f"{sid}.npz").exists():
        save_population(sid, entry["candidates"])
    s = Strip(sid)
    cals = s.cals[0.0]
    at_cap = int(np.isnan(hc.rates_by_other(cals, s.branch, s.raw, hc.colour(s.row, s.col, s.scale))[0]).sum())
    if sid in reference and reference[sid]["at_cap_in_strip"] != at_cap:
        raise RuntimeError(f"{sid}: {at_cap} at the cap, item 15 counted {reference[sid]['at_cap_in_strip']}")
    cands = entry["candidates"]
    raw = raws_of(s, cands)
    colours = hc.colour([c["row"] for c in cands], [c["col"] for c in cands], s.scale)
    rate, below = hc.rates_by_other(cals, np.array([c["branch"] for c in cands]), raw, colours)
    out = hc.with_rate_column(cands, rate, below)
    if not hc.only_the_column_differs(cands, out):
        raise RuntimeError(f"{sid}: the column changed something else in the list")
    measured = rate[np.isfinite(rate)]
    return out, {
        "rows": len(out),
        "rows_at_cap": int(np.isnan(rate).sum()),
        "population": len(s.raw),
        "population_at_cap": at_cap,
        "checked_against_item_15": sid in reference,
        "area_km2_by_colour": [round(x, 2) for x in s.area[0.0]],
        "rate_per_km2_min_median_max": (
            [float(f"{x:.3g}") for x in (measured.min(), np.median(measured), measured.max())] if len(measured) else None
        ),
    }


def rate_column(a) -> int:
    sites, _, _ = rr.controls()
    out_dir = OUT / "column"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.json"
    summary = rr.load(summary_path) if summary_path.exists() else {"lists": {}}
    reference = rr.load(OUT / "results.json")["top20_makeup"]
    for path in map(Path, a.lists):
        out = out_dir / path.name
        if path.name in summary["lists"] and out.exists():
            continue
        d = rr.load(path)
        for sid in d["strips"]:
            ex.refuse_blind(sites, sid)
        record = {}
        for sid, entry in d["strips"].items():
            entry["candidates"], record[sid] = strip_column(sid, entry, reference)
        d["half_rate_column"] = {
            "what": f"{hc.RATE_FIELD}: candidates per km2 of this strip, in this candidate's branch, at or above its raw "
            f"score, measured on the half of the strip it does not sit on; no rule gain. {hc.BELOW_FIELD}: above the top "
            "of that curve, where the data say only that the rate is below this. Beside the score only: no order and no "
            "grade comes from it.",
            "git": run.git_state(),
        }
        rr.write_json(out, d)
        summary["git"] = run.git_state()
        summary["lists"][path.name] = record
        rr.write_json(summary_path, summary)
        print(f"{path.name}: {sum(r['rows'] for r in record.values())} rows", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pop")
    sub.add_parser("redetect")
    f = sub.add_parser("score")
    f.add_argument("--no-texture", nargs="*", default=[], help="target strips with no ground texture, reported apart")
    c = sub.add_parser("column")
    c.add_argument("lists", nargs="+", help="candidates files, each with a strips section")
    a = ap.parse_args(argv)
    return {"pop": population, "redetect": redetect, "score": score_all, "column": rate_column}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
