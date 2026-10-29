"""Scratch: why a sheet candidate present in v0.1 is missing in v0.2 at one recorded piece. Runs the sheet branch
on a window around the piece with both saturation treatments and prints the reduced-resolution components
near it (flatness, peak, mean, extent) and the detector's own sheet candidates. Reads the key; not pipeline.

    uv run --env-file out/landers.env experiments/sheet_saturation.py schiaparelli parachute
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.detect import DetectorConfig, area_range_px, block_mean, components, detect_tile, local_z  # noqa: E402
from landers.strip import SATURATED, Strip  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("site")
    ap.add_argument("piece")
    ap.add_argument("--window", type=int, default=1024)
    ap.add_argument("--radius", type=float, default=40.0)
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--tiled", action="store_true", help="use the detector's own 2048/128 tiles that contain the piece")
    a = ap.parse_args(argv)
    key = json.loads(Path(a.answers).read_text())
    pc = next(p for s in key["sites"] if s["name"] == a.site for p in s["pieces"] if p["piece"] == a.piece)
    row, col = float(pc["line"]) - 1, float(pc["sample"]) - 1
    strip = Strip.open(pc["strip"])
    lbl = strip.label
    wins = []
    if a.tiled:
        cfg0 = DetectorConfig()
        for r0, r1, c0, c1 in strip.tiles(cfg0.tile, cfg0.overlap):
            if r0 <= row < r1 and c0 <= col < c1:
                wins.append(strip.read(r0, r1, c0, c1))
    else:
        wins.append(strip.read_centered(row, col, a.window))
    for win in wins:
        analyse(win, row, col, lbl, a)
    return 0


def analyse(win, row, col, lbl, a):
    r, c = row - win.row0, col - win.col0
    print(f"\n#### window rows {win.row0}+{win.shape[0]} cols {win.col0}+{win.shape[1]}; piece at ({r:.0f}, {c:.0f}) in it")
    sat = win.data >= SATURATED
    print(f"window {win.shape}, saturated px in window: {int(sat.sum())}, within 20 px of piece: "
          f"{int(sat[int(r)-20:int(r)+21, int(c)-20:int(c)+21].sum())}")
    for name, sat_is_data in (("v0.1 mask (saturated = no-data)", False), ("v0.2 mask (saturated = data)", True)):
        cfg = DetectorConfig(saturated_is_data=sat_is_data)
        usable = (win.valid | sat) if sat_is_data else win.valid
        n = cfg.sheet_reduce
        scale = lbl.scale_m
        d_r, v_r = block_mean(win.data, usable, n)
        z_r = local_z(d_r, v_r, cfg.sheet_background_px, cfg.sheet_sigma, cfg.sheet_inner_px, margin=2)
        rr, cc = r / n, c / n
        print(f"\n== {name}")
        print(f"   reduced z at piece {z_r[int(rr), int(cc)]:.2f}; max within 5 reduced px "
              f"{z_r[int(rr)-5:int(rr)+6, int(cc)-5:int(cc)+6].max():.2f}; valid blocks within 5: "
              f"{int(v_r[int(rr)-5:int(rr)+6, int(cc)-5:int(cc)+6].sum())}/121")
        comps, _ = components(z_r > cfg.z_sheet, z_r, area_range_px(cfg.sheet_size_m, scale * n), v_r,
                              max(2, cfg.edge_margin_px // n))
        near = [k for k in comps if math.hypot(k.row - rr, k.col - cc) * n <= a.radius]
        for k in near:
            flat = k.mean / k.peak if k.peak > 0 else 0.0
            print(f"   sheet component: d={math.hypot(k.row - rr, k.col - cc) * n:.1f} px area={k.area * n * n} px "
                  f"extent={max(k.bbox_h, k.bbox_w) * scale * n:.1f} m peak={k.peak:.2f} mean={k.mean:.2f} "
                  f"flatness={flat:.2f} ({'kept' if flat >= cfg.sheet_flatness else 'dropped: flatness < ' + str(cfg.sheet_flatness)})")
        if not near:
            print("   no reduced component above z_sheet within radius")
        cands = detect_tile(win, lbl, cfg)
        for cd in sorted(cands, key=lambda x: -x.score):
            d = math.hypot(cd.row - row, cd.col - col)  # candidates carry strip coordinates
            if d <= a.radius:
                ex = {k: v for k, v in cd.extra.items() if k in ("flatness", "extent_m", "saturated_px", "two_sided")}
                print(f"   candidate {cd.branch:12s} raw score {cd.score:6.2f} d={d:5.1f} px area={cd.area_px} {ex}")


if __name__ == "__main__":
    raise SystemExit(main())
