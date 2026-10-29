"""Transplant injection score: the recorded pieces of the tuning sites, cut at full resolution from their
strips and planted into tiles of the search strips with the nearest sun, detected, and scored as recall
at the thresholds' false-alarm rate. The scoreboard for tuning (docs/plan.md item 7).

    uv run scripts/transplant.py --run t1
    uv run scripts/transplant.py --run t2 --copies 6 --nearest 4 --tiles-per-strip 6 --seed 1
    uv run scripts/transplant.py --run raw --no-calibration

Writes out/transplant_<run>/transplant_<run>.json (cuts, placements, detections, the score), cuts.png
(each cut at the source beside one planting) and placements.png (every planting under one stretch).
Sources are tuning strips only; targets are search-area strips of the same scale; held-out, spare and
final-exam strips are never touched. No model is called.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers import transplant as tp  # noqa: E402
from landers.detect import DetectorConfig, detect_tile, finish_tile, load_calibration, load_shape_rules  # noqa: E402
from landers.score import format_injection_report, load_json, match_radius_px, recall_at_false_alarm_rate  # noqa: E402
from landers.sheets import CREDIT, apply_stretch, stretch_limits  # noqa: E402
from landers.strip import Strip  # noqa: E402

DEFAULT_CAL = config.REPO_ROOT / "landers" / "calibration_v0.json"
_RULE_FILES = sorted((config.REPO_ROOT / "landers").glob("shape_v*.json"))
DEFAULT_RULES = _RULE_FILES[-1] if _RULE_FILES else None


def repo_relative(path: str) -> str:
    p = Path(path).resolve()
    return str(p.relative_to(config.REPO_ROOT)) if p.is_relative_to(config.REPO_ROOT) else path


def pick_tiles(strip: Strip, dcfg: DetectorConfig, n: int, min_valid: float, rng: np.random.Generator):
    """``n`` tile bounds spread along the strip's footprint whose overview says they are mostly valid;
    a seeded jitter so different seeds see different ground."""
    tiles = list(strip.tiles(dcfg.tile, dcfg.overlap, min_valid_fraction=min_valid))
    if len(tiles) <= n:
        return tiles
    idx = np.linspace(0, len(tiles) - 1, n + 1)[:-1]
    idx = (idx + rng.uniform(0, idx[1] - idx[0], size=n)).round().astype(int)
    return [tiles[i] for i in sorted(set(int(i) for i in idx))]


def crop(data: np.ndarray, valid: np.ndarray, r: int, c: int, half: int):
    r0, c0 = max(r - half, 0), max(c - half, 0)
    r1, c1 = min(r + half + 1, data.shape[0]), min(c + half + 1, data.shape[1])
    return data[r0:r1, c0:c1], valid[r0:r1, c0:c1]


def render_pairs(rows: list[tuple[tuple, tuple, str]], limits_left, limits_right, title: str, out: Path):
    """One cell per cut: the source disc (left), one planting (right), each a (data, valid) pair drawn
    under its sheet's stretch."""
    if not rows:
        return
    size = max(max(a[0].shape[0], b[0].shape[0]) for a, b, _ in rows)
    size = min(max(size, 48), 160)
    zoom = 2 if size <= 80 else 1
    cell = size * zoom
    cols = 2
    per_row = 4  # cuts per sheet row
    n_rows = -(-len(rows) // per_row)
    width = per_row * (cols * cell + 12)
    sheet = Image.new("RGB", (width, n_rows * (cell + 30) + 60), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, (a, b, label) in enumerate(rows):
        x0 = (i % per_row) * (cols * cell + 12)
        y0 = (i // per_row) * (cell + 30)
        for j, (img, lim) in enumerate(((a, limits_left), (b, limits_right))):
            arr, v = img
            im = Image.fromarray(apply_stretch(arr, v, lim)).convert("RGB")
            im = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
            sheet.paste(im, (x0 + j * cell, y0))
        d.text((x0 + 2, y0 + cell + 2), label, fill=(255, 220, 0))
    fy = n_rows * (cell + 30)
    d.text((4, fy + 4), title, fill=(255, 255, 255))
    ll = f"{limits_left[0]:.0f}..{limits_left[1]:.0f}" if limits_left else "none"
    lr = f"{limits_right[0]:.0f}..{limits_right[1]:.0f}" if limits_right else "none"
    d.text(
        (4, fy + 20),
        f"Credit: {CREDIT}. Left: the cut at its source (stretch {ll} DN over all left panels). "
        f"Right: the same cut planted in search-area ground (stretch {lr} DN over all right panels). Full resolution.",
        fill=(200, 200, 200),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--copies", type=int, default=4, help="plantings of each cut (real and sham)")
    ap.add_argument("--nearest", type=int, default=4, help="target strips per source, nearest tan(incidence)")
    ap.add_argument("--tiles-per-strip", type=int, default=6)
    ap.add_argument("--min-valid", type=float, default=0.7, help="a tile's overview must be this valid")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fa-per-km2", type=float, default=None, help="default: thresholds pass.max_false_alarms_per_km2")
    ap.add_argument("--calibration", default=str(DEFAULT_CAL) if DEFAULT_CAL.exists() else None)
    ap.add_argument("--no-calibration", action="store_true", help="raw branch scores")
    ap.add_argument(
        "--shape-rules",
        default=str(DEFAULT_RULES) if DEFAULT_RULES else None,
        help="shape rules JSON added to the calibrated score (default: the newest landers/shape_v*.json, as "
        "scripts/detect.py); every detection records its features either way, so scripts/tune.py can apply "
        "other rules to an unruled run without re-detecting",
    )
    ap.add_argument("--no-shape-rules", action="store_true", help="record shape features, add nothing to the score")
    ap.add_argument("--no-sham", action="store_true", help="skip the sham (empty) cuts")
    ap.add_argument("--only", action="append", default=[], help="site/piece to cut (repeatable); default all")
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out"))
    a = ap.parse_args(argv)

    t0 = time.time()
    sites = load_json(a.sites)
    thresholds = load_json(a.thresholds)
    answers = load_json(a.answers)
    fa = a.fa_per_km2 if a.fa_per_km2 is not None else float(thresholds["pass"]["max_false_alarms_per_km2"])
    cfg = tp.TransplantConfig()
    cal_path = None if a.no_calibration else a.calibration
    rules_path = None if a.no_shape_rules else a.shape_rules
    dcfg = DetectorConfig(calibration=cal_path, shape_rules=rules_path)
    cal = load_calibration(dcfg)
    rules = load_shape_rules(dcfg)
    if cal is not None:
        dcfg.calibration = repo_relative(cal_path)
    if rules is not None:
        dcfg.shape_rules = repo_relative(rules_path)
    rng = np.random.default_rng(a.seed)

    allowed = tp.tuning_sources(sites)
    pieces = tp.key_pieces(answers, thresholds, allowed)
    if a.only:
        pieces = [p for p in pieces if f"{p['site']}/{p['piece']}" in a.only]
    if not pieces:
        print("no recorded pieces to cut", file=sys.stderr)
        return 2
    target_ids = tp.search_targets(sites, config.manifest_path().read_text())
    target_labels = tp.load_labels(target_ids)
    if not target_labels:
        print("no search strips on disk", file=sys.stderr)
        return 2

    # 1. cut
    cuts: list[tp.Cut] = []
    skipped: list[str] = []
    by_strip: dict[str, list[dict]] = {}
    for p in pieces:
        by_strip.setdefault(p["strip"], []).append(p)
    source_labels: dict[str, object] = {}
    for sid, plist in by_strip.items():
        if config.find_strip(sid) is None:
            skipped.extend(f"{p['site']}/{p['piece']}: source strip not on disk" for p in plist)
            continue
        strip = Strip.open(sid)
        source_labels[sid] = strip.label
        all_pos = [(p["row"], p["col"]) for p in plist]
        for p in plist:
            cut = tp.cut_piece(strip, p["site"], p["piece"], p["kind"], p["row"], p["col"], p["size_m"], cfg)
            if cut is None:
                skipped.append(f"{p['site']}/{p['piece']}: could not cut (edge or no ground for a background)")
                continue
            cut.other_pieces_in_cut = [
                q["piece"]
                for q in plist
                if q is not p and math.hypot(q["row"] - p["row"], q["col"] - p["col"]) <= cut.radius_px
            ]
            cuts.append(cut)
            print(
                f"cut {p['site']}/{p['piece']}: radius {cut.radius_px} px, background {cut.background_dn:.0f} DN, "
                f"{cut.n_saturated} saturated px"
                + (f", also holds {cut.other_pieces_in_cut}" if cut.other_pieces_in_cut else "")
            )
            if a.no_sham:
                continue
            pos = tp.sham_position(strip, p["row"], p["col"], cut.radius_px, all_pos, cfg)
            if pos is None:
                skipped.append(f"{p['site']}/{p['piece']}: no sham position found")
                continue
            sham = tp.cut_piece(strip, p["site"], p["piece"], p["kind"], pos[0], pos[1], p["size_m"], cfg, sham=True)
            if sham is None:
                skipped.append(f"{p['site']}/{p['piece']}: sham cut failed")
                continue
            cuts.append(sham)
        del strip
    if not cuts:
        print("nothing was cut", file=sys.stderr)
        return 2

    # 2. targets per source, tiles per target
    targets_of: dict[str, list[str]] = {}
    for sid, lbl in source_labels.items():
        targets_of[sid] = tp.nearest_targets(lbl, target_labels, a.nearest)
        if not targets_of[sid]:
            skipped.append(f"source {sid}: no search strip at its map scale")
    tile_plan: dict[str, list[tuple[int, int, int, int]]] = {}
    tile_ids: list[str] = []
    tile_bounds: dict[str, tuple[str, tuple[int, int, int, int]]] = {}
    open_targets: dict[str, Strip] = {}
    for tid in sorted({t for ts in targets_of.values() for t in ts}):
        strip = Strip.open(tid)
        open_targets[tid] = strip
        tile_plan[tid] = pick_tiles(strip, dcfg, a.tiles_per_strip, a.min_valid, rng)
        for b in tile_plan[tid]:
            key = f"{tid}:{b[0]}:{b[2]}"
            tile_ids.append(key)
            tile_bounds[key] = (tid, b)
        lbl = strip.label
        print(
            f"target {tid}: incidence {lbl.incidence_deg:.2f}, azimuth {lbl.sub_solar_azimuth_deg:.2f}, "
            f"{len(tile_plan[tid])} tiles"
        )

    # 3. assign every copy of every cut to a tile of one of its source's targets
    per_tile: dict[str, list[int]] = {k: [] for k in tile_ids}
    for ci, cut in enumerate(cuts):
        choices = [k for k in tile_ids if tile_bounds[k][0] in targets_of.get(cut.source, [])]
        if not choices:
            continue
        order = rng.permutation(len(choices))
        for k in range(a.copies):
            per_tile[choices[int(order[k % len(choices)])]].append(ci)

    # 4. plant, detect
    detections: list[dict] = []
    placements: list[tp.Placement] = []
    area_km2 = 0.0
    pair_rows: dict[int, tuple] = {}
    planted_crops: list[tuple[np.ndarray, np.ndarray, str, int]] = []
    tiles_done = 0
    for key in tile_ids:
        idxs = per_tile[key]
        if not idxs:
            continue
        tid, (r0, r1, c0, c1) = tile_bounds[key]
        strip = open_targets[tid]
        win = strip.read(r0, r1, c0, c1)
        if win.valid.mean() < a.min_valid:
            continue
        rng.shuffle(idxs)
        planted, placed = tp.place_in_tile(win, strip.label, cuts, idxs, rng, cfg, key)
        cands = finish_tile(detect_tile(planted, strip.label, dcfg), dcfg, cal, rules)
        for c in cands:
            d = {
                "tile": key,
                "row": round(c.row - r0, 1),
                "col": round(c.col - c0, 1),
                "score": round(c.score, 4),
                "branch": c.branch,
                "area_px": c.area_px,
            }
            if "raw_score" in c.extra:
                d["raw_score"] = c.extra["raw_score"]
            feats = {k: v for k, v in c.extra.items() if k != "raw_score"}
            if feats:
                d["features"] = feats
            detections.append(d)
        placements.extend(placed)
        for p in placed:
            cr = crop(planted.data, planted.valid, int(p.row), int(p.col), cuts[p.cut_index].half + 8)
            label = f"{p.site}/{p.piece}{' sham' if p.sham else ''} r{p.rotation_deg:+.0f}"
            planted_crops.append((cr[0], cr[1], label, p.cut_index))
            if p.cut_index not in pair_rows:
                pair_rows[p.cut_index] = cr
        area_km2 += float(win.valid.sum()) * strip.label.scale_m**2 / 1e6
        tiles_done += 1
        print(f"{key}: {len(placed)}/{len(idxs)} planted, {len(cands)} detections, {time.time() - t0:.0f}s")

    # 5. score
    def radius_for(p: tp.Placement) -> float:
        return match_radius_px(thresholds, cuts[p.cut_index].scale_m, p.kind)

    truths = []
    for i, p in enumerate(placements):
        if p.sham:
            continue
        truths.append(
            {
                "tile": p.tile,
                "row": p.row,
                "col": p.col,
                "kind": p.kind,
                "site": p.site,
                "piece": p.piece,
                "size_m": cuts[p.cut_index].size_m,
                "radius_px": radius_for(p),
                "placement": i,
            }
        )
    radius_default = match_radius_px(thresholds, 0.25) if thresholds else 20.0

    def scored(group):
        return recall_at_false_alarm_rate(detections, truths, area_km2, radius_default, fa, group=group)

    by_piece = scored(lambda t: (t["kind"], f"{t['site']}/{t['piece']}"))
    by_kind = scored(lambda t: (t["kind"], "all"))
    by_site = scored(lambda t: (t["kind"], t["site"]))
    thr = by_piece["score_threshold"]
    shams = tp.sham_hits(detections, placements, thr, radius_for)
    # per placement: the best detection within its radius among all detections, and its rank in the tile
    by_tile: dict[str, list[dict]] = {}
    for d in detections:
        by_tile.setdefault(d["tile"], []).append(d)
    for lst in by_tile.values():
        lst.sort(key=lambda d: -d["score"])
    placement_rows = []
    for p in placements:
        r = radius_for(p)
        best = None
        for rank, d in enumerate(by_tile.get(p.tile, []), start=1):
            dist = math.hypot(d["row"] - p.row, d["col"] - p.col)
            if dist <= r:
                best = {"rank_in_tile": rank, "score": d["score"], "branch": d["branch"], "distance_px": round(dist, 1)}
                break
        row = p.to_json()
        row["match_radius_px"] = r
        row["best"] = best
        row["found_at_threshold"] = bool(best is not None and (thr is None or best["score"] > thr))
        placement_rows.append(row)

    result = {
        "run": a.run,
        "kind": "transplant",
        "detector": dcfg.to_json(),
        "transplant": cfg.to_json(),
        "seed": a.seed,
        "copies": a.copies,
        "nearest": a.nearest,
        "tiles_per_strip": a.tiles_per_strip,
        "fa_per_km2_target": fa,
        "area_km2": round(area_km2, 4),
        "n_tiles": tiles_done,
        "targets_of": targets_of,
        "targets": {
            tid: {
                "incidence_deg": s.label.incidence_deg,
                "tan_incidence": round(math.tan(math.radians(s.label.incidence_deg)), 3),
                "sub_solar_azimuth_deg": s.label.sub_solar_azimuth_deg,
                "scale_m": s.label.scale_m,
                "tiles": [list(b) for b in tile_plan[tid]],
            }
            for tid, s in open_targets.items()
        },
        "sources": {
            sid: {
                "incidence_deg": lbl.incidence_deg,
                "tan_incidence": round(math.tan(math.radians(lbl.incidence_deg)), 3),
                "sub_solar_azimuth_deg": lbl.sub_solar_azimuth_deg,
                "scale_m": lbl.scale_m,
            }
            for sid, lbl in source_labels.items()
        },
        "cuts": [c.to_json() for c in cuts],
        "n_cuts": sum(1 for c in cuts if not c.sham),
        "n_sham_cuts": sum(1 for c in cuts if c.sham),
        "n_placements": sum(1 for p in placements if not p.sham),
        "n_sham_placements": sum(1 for p in placements if p.sham),
        "tan_ratio": {
            "min": round(min((p.tan_ratio for p in placements), default=0.0), 3),
            "max": round(max((p.tan_ratio for p in placements), default=0.0), 3),
        },
        "score": by_piece,
        "score_by_kind": by_kind,
        "score_by_site": by_site,
        "sham": shams,
        "placements": placement_rows,
        "detections": detections,
        "skipped": skipped,
        "seconds": round(time.time() - t0),
    }
    out_dir = Path(a.out) / f"transplant_{a.run}"
    tp.write_json(out_dir / f"transplant_{a.run}.json", result)

    # 6. sheets
    source_panels = []
    for ci, c in enumerate(cuts):
        src = (np.clip(c.gain * c.background_dn, 0, 1023).astype(np.uint16), np.ones(c.gain.shape, bool))
        if ci in pair_rows:
            source_panels.append((src, pair_rows[ci], f"{c.site}/{c.piece}{' sham' if c.sham else ''}"))
    if source_panels:
        ll = stretch_limits([s for s, _, _ in source_panels])
        lr = stretch_limits([t for _, t, _ in source_panels])
        title = f"transplant {a.run}: each cut at its source and one planting"
        render_pairs(source_panels, ll, lr, title, out_dir / "cuts.png")
    if planted_crops:
        lim = stretch_limits([(d, v) for d, v, _, _ in planted_crops])
        rows = [((d, v), (d, v), label) for d, v, label, _ in planted_crops]
        title = f"transplant {a.run}: every planting (shown twice) under one stretch"
        render_pairs(rows, lim, lim, title, out_dir / "placements.png")

    print()
    print(
        f"transplant {a.run}: {result['n_cuts']} cuts, {result['n_sham_cuts']} shams, "
        f"{result['n_placements']} plantings on {tiles_done} tiles, {area_km2:.3f} km2"
    )
    print(format_injection_report(by_piece))
    print()
    print("by kind:")
    print(format_injection_report(by_kind))
    print()
    print(f"sham: {shams['hit']} of {shams['n']} shams have a kept detection within their radius ({shams['rate']})")
    print(f"tan ratio target/source: {result['tan_ratio']['min']} to {result['tan_ratio']['max']}")
    if skipped:
        print("skipped:")
        for s in skipped:
            print("  " + s)
    print(f"\nwritten: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
