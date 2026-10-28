"""Injection score: synthetic sheets, dark compacts and blob-plus-shadow objects of known size drawn into
real tiles of tuning or spare strips, then detected and scored as recall by size and branch at the
false-alarm rate in controls/thresholds.json.

    uv run scripts/inject.py --site viking1 --tiles 4 --per-kind 3 --run inj1
    uv run scripts/inject.py <observation id> ... --fa-per-km2 2.0
    uv run scripts/inject.py --site viking1 --tile-phase 1 --calibration landers/calibration_v0.json

--tile-phase 0 and 1 pick two interleaved sets of tiles, so a calibration fitted on phase 0 can be
evaluated on phase 1. The output carries the raw detections and truths for scripts/calibrate.py.

Refuses strips of held-out and final-exam sites and anything not listed under a tuning or spare site,
so the search area is never used. Writes out/inject_<run>.json.
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
from landers.detect import DetectorConfig, detect_tile, load_calibration  # noqa: E402
from landers.inject import InjectConfig, inject  # noqa: E402
from landers.score import format_injection_report, load_json, match_radius_px, recall_at_false_alarm_rate  # noqa: E402
from landers.strip import Strip  # noqa: E402


def allowed_strips(sites_path: Path) -> dict[str, str]:
    out = {}
    for s in json.loads(sites_path.read_text())["sites"]:
        if s["group"] in ("tuning", "spare"):
            for sid in s["strips"]:
                out[sid] = s["name"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--site", action="append", default=[])
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--fa-per-km2", type=float, default=None, help="default: thresholds pass.max_false_alarms_per_km2")
    ap.add_argument("--tiles", type=int, default=4, help="tiles per strip, spread over the footprint")
    ap.add_argument("--per-kind", type=int, default=3, help="objects of each kind per tile")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tile-phase", type=int, default=0, choices=(0, 1), help="which of two interleaved tile sets")
    ap.add_argument("--calibration", default=None, help="apply this calibration before scoring")
    ap.add_argument("--run", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out"))
    a = ap.parse_args(argv)

    allowed = allowed_strips(Path(a.sites))
    ids = list(a.ids)
    for name in a.site:
        ids.extend(sid for sid, site in allowed.items() if site == name)
    if not ids:
        ap.error("no strips given")
    for sid in ids:
        if sid not in allowed:
            print(f"{sid}: not a tuning or spare strip; refused", file=sys.stderr)
            return 3
    thresholds = load_json(a.thresholds) if Path(a.thresholds).exists() else {}
    fa = a.fa_per_km2 if a.fa_per_km2 is not None else float(thresholds["pass"]["max_false_alarms_per_km2"])
    dcfg, icfg = DetectorConfig(calibration=a.calibration), InjectConfig()
    cal = load_calibration(dcfg)
    if cal is not None:
        from landers.calibrate import apply
    rng = np.random.default_rng(a.seed)
    detections, truths = [], []
    area_km2 = 0.0
    radius_px = None
    t0 = time.time()
    for sid in ids:
        if config.find_strip(sid) is None:
            print(f"{sid}: not on disk, skipped")
            continue
        strip = Strip.open(sid)
        r_px = match_radius_px(thresholds, strip.label.scale_m) if thresholds else 20.0
        radius_px = r_px if radius_px is None else min(radius_px, r_px)
        tiles = list(strip.tiles(dcfg.tile, dcfg.overlap))
        want = min(2 * a.tiles, len(tiles))
        both = np.linspace(0, len(tiles) - 1, want).round().astype(int)
        pick = [tiles[i] for i in both[a.tile_phase :: 2]]
        for n, (r0, r1, c0, c1) in enumerate(pick):
            win = strip.read(r0, r1, c0, c1)
            if win.valid.mean() < 0.5:
                continue
            tile_id = f"{sid}:{r0}:{c0}"
            injected, objs = inject(win, strip.label, icfg, rng, a.per_kind)
            tile_cands = detect_tile(injected, strip.label, dcfg)
            if cal is not None:
                tile_cands = apply(tile_cands, cal)
            for c in tile_cands:
                detections.append(
                    {"tile": tile_id, "row": c.row - r0, "col": c.col - c0, "score": c.score, "branch": c.branch}
                )
            for o in objs:
                d = o.to_json()
                d["tile"] = tile_id
                truths.append(d)
            area_km2 += float(win.valid.sum()) * strip.label.scale_m**2 / 1e6
            print(f"{sid} tile {n + 1}/{len(pick)}: {len(objs)} objects injected, {len(detections)} detections so far")
    result = recall_at_false_alarm_rate(detections, truths, area_km2, radius_px or 20.0, fa)
    result.update(
        {
            "run": a.run,
            "detector": dcfg.to_json(),
            "injection": icfg.to_json(),
            "seed": a.seed,
            "tile_phase": a.tile_phase,
            "match_radius_px": radius_px,
            "n_tiles": len({t["tile"] for t in truths}),
            "sites": sorted({allowed[s] for s in ids}),
            "seconds": round(time.time() - t0),
            "detections": [
                dict(d, row=round(d["row"], 1), col=round(d["col"], 1), score=round(d["score"], 4)) for d in detections
            ],
            "truths": truths,
        }
    )
    out = Path(a.out) / f"inject_{a.run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(format_injection_report(result))
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
