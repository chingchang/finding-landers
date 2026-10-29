"""Per-strip rarity curves for strips that a run detects on by the tile (the transplant board), fitted from
a raw detector pass over other tiles of the same strips (plan item 8a, detector v0.4 calibration_mode
per_strip).

    uv run scripts/calibrate_strips.py --from-transplant out/transplant_t4/transplant_t4.json --tiles 12 --name t4
    uv run scripts/calibrate_strips.py <observation id> ... --tiles 12 --name x

With --from-transplant the strips are the run's targets and the run's planted tiles are left out, so the
curve a planting is scored by was fitted on ground it does not sit on. Each strip's fit is what
``scripts/detect.py --per-strip`` does on a whole strip, on a sample of its tiles. Held-out and final-exam
strips are refused. Writes out/strip_cal/<name>/strip_calibration_<name>.json (landers.calibrate
StripCalibrations) with the tiles each curve came from; the file names strips and stays under out/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.calibrate import StripCalibrations, fit_scores  # noqa: E402
from landers.detect import DetectorConfig, detect_tile  # noqa: E402
from landers.score import load_json  # noqa: E402
from landers.strip import Strip  # noqa: E402


def sealed_strips(sites: dict) -> set[str]:
    return {sid for s in sites["sites"] if s["group"] in ("heldout", "final_exam") for sid in s["strips"]}


def pick_tiles(strip: Strip, dcfg: DetectorConfig, n: int, min_valid: float, exclude: set[tuple]):
    """``n`` tiles spread along the footprint, none of them in ``exclude`` (exact bounds)."""
    tiles = [b for b in strip.tiles(dcfg.tile, dcfg.overlap, min_valid_fraction=min_valid) if tuple(b) not in exclude]
    if len(tiles) <= n:
        return tiles
    idx = np.linspace(0, len(tiles) - 1, n).round().astype(int)
    return [tiles[i] for i in sorted(set(int(i) for i in idx))]


def fit_strip_from_tiles(
    strip: Strip, bounds: list[tuple], dcfg: DetectorConfig, min_valid: float, top_exclude: int, min_population: int = 0
):
    """Raw detections over the tiles, pooled per branch, fitted as one curve for the strip."""
    by_branch: dict[str, list[float]] = {}
    area = 0.0
    used = []
    for r0, r1, c0, c1 in bounds:
        win = strip.read(r0, r1, c0, c1)
        if win.valid.mean() < min_valid:
            continue
        for c in detect_tile(win, strip.label, dcfg):
            by_branch.setdefault(c.branch, []).append(float(c.score))
        area += float(win.valid.sum()) * strip.label.scale_m**2 / 1e6
        used.append([r0, r1, c0, c1])
    if area <= 0:
        return None, used, by_branch
    cal = fit_scores(
        by_branch, area, "per_strip", len(used), [], top_exclude=top_exclude, min_population=min_population
    )
    return cal, used, by_branch


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="observation ids")
    ap.add_argument("--from-transplant", default=None, help="a transplant run: its targets, minus its planted tiles")
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--tiles", type=int, default=12, help="tiles per strip")
    ap.add_argument("--min-valid", type=float, default=0.7)
    ap.add_argument("--top-exclude", type=int, default=0)
    ap.add_argument(
        "--min-population",
        type=int,
        default=0,
        help="a branch with fewer candidates than this on a strip gets no curve; the run that applies the file "
        "scores it by its table (scripts/transplant.py --calibration)",
    )
    ap.add_argument("--name", required=True)
    ap.add_argument(
        "--refit-from", default=None, help="an earlier output: refit its raw scores with this --top-exclude"
    )
    ap.add_argument(
        "--pooled",
        action="store_true",
        help="with --refit-from: one curve set from every strip's raw scores pooled (a terrain-class table), "
        "written under each strip id so the same file format applies it",
    )
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out" / "strip_cal"))
    a = ap.parse_args(argv)

    if a.refit_from:
        return refit(a)
    sealed = sealed_strips(load_json(a.sites))
    ids = list(a.ids)
    exclude: dict[str, set[tuple]] = {}
    if a.from_transplant:
        run = load_json(a.from_transplant)
        for tid, t in run["targets"].items():
            ids.append(tid)
            exclude[tid] = {tuple(b) for b in t["tiles"]}
    if not ids:
        ap.error("no strips given")
    for sid in ids:
        if sid in sealed:
            print(f"{sid}: held-out or final-exam strip; refused", file=sys.stderr)
            return 3
    dcfg = DetectorConfig(calibration=None, shape_rules=None)
    t0 = time.time()
    strips: dict = {}
    fit_tiles: dict = {}
    counts: dict = {}
    raw_scores: dict = {}
    for sid in ids:
        if config.find_strip(sid) is None:
            print(f"{sid}: not on disk, skipped")
            continue
        strip = Strip.open(sid)
        bounds = pick_tiles(strip, dcfg, a.tiles, a.min_valid, exclude.get(sid, set()))
        cal, used, by_branch = fit_strip_from_tiles(strip, bounds, dcfg, a.min_valid, a.top_exclude, a.min_population)
        if cal is None:
            print(f"{sid}: no valid tile; skipped")
            continue
        strips[sid] = cal
        fit_tiles[sid] = used
        counts[sid] = {b: len(v) for b, v in sorted(by_branch.items())}
        raw_scores[sid] = {b: [round(x, 4) for x in v] for b, v in sorted(by_branch.items())}
        print(
            f"{sid}: {len(used)} tiles, {cal.area_km2:.3f} km2, "
            + ", ".join(f"{b} {n}" for b, n in counts[sid].items())
            + f", {time.time() - t0:.0f}s"
        )
        del strip
    if not strips:
        print("nothing fitted", file=sys.stderr)
        return 2
    sc = StripCalibrations(
        f"per_strip_{a.name}",
        strips,
        a.top_exclude,
        basis=f"scripts/calibrate_strips.py: {a.tiles} tiles per strip, raw detector {dcfg.version}, "
        + (f"excluding the planted tiles of {a.from_transplant}" if a.from_transplant else "no tiles excluded"),
        min_population=a.min_population,
    )
    out_dir = Path(a.out) / a.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"strip_calibration_{a.name}.json"
    d = sc.to_json()
    d["fit_tiles"] = fit_tiles
    d["raw_counts"] = counts
    d["raw_scores"] = raw_scores
    d["seconds"] = round(time.time() - t0)
    out.write_text(json.dumps(d, indent=1))
    print(f"written: {out}")
    return 0


def refit(a) -> int:
    """The same strips and tiles, refitted from the recorded raw scores with another ``top_exclude``."""
    d = load_json(a.refit_from)
    strips = {}
    if a.pooled:
        pooled: dict[str, list[float]] = {}
        area = 0.0
        n_tiles = 0
        for sid, by_branch in d["raw_scores"].items():
            for b, v in by_branch.items():
                pooled.setdefault(b, []).extend(v)
            area += float(d["strips"][sid]["area_km2"])
            n_tiles += len(d["fit_tiles"][sid])
        one = fit_scores(
            pooled, area, "pooled", n_tiles, [], top_exclude=a.top_exclude, min_population=a.min_population
        )
        strips = {sid: one for sid in d["raw_scores"]}
    else:
        for sid, by_branch in d["raw_scores"].items():
            area = float(d["strips"][sid]["area_km2"])
            strips[sid] = fit_scores(
                by_branch,
                area,
                "per_strip",
                len(d["fit_tiles"][sid]),
                [],
                top_exclude=a.top_exclude,
                min_population=a.min_population,
            )
    sc = StripCalibrations(
        f"{'pooled' if a.pooled else 'per_strip'}_{a.name}",
        strips,
        a.top_exclude,
        basis=f"{d['basis']}; refit from {a.refit_from}"
        + ("; one curve set pooled over the strips" if a.pooled else ""),
        min_population=a.min_population,
    )
    out_dir = Path(a.out) / a.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"strip_calibration_{a.name}.json"
    new = sc.to_json()
    for k in ("fit_tiles", "raw_counts", "raw_scores"):
        new[k] = d[k]
    out.write_text(json.dumps(new, indent=1))
    how = "pooled over" if a.pooled else "per strip for"
    print(f"refit {how} {len(strips)} strips, top_exclude {a.top_exclude}, min_population {a.min_population}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
