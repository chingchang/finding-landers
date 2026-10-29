"""Scratch: what the detector's z-map looks like around each recorded piece in the key, so shape tests
can be designed on what is there rather than guessed. Reads the key; not part of the pipeline.

    uv run --env-file out/landers.env experiments/piece_zoom.py --out out/shape_v1/piece_zoom.json

For each recorded piece: the bright (z > 4) and dark (z < -3.5) components within 40 px of the recorded
position with their areas and peak z, the mean z profile along the label's shadow direction (sun side
negative, anti-sun side positive) in 2 px steps out to 40 px, and how many bright components sit within
100 px (isolation).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config, geo  # noqa: E402
from landers.detect import DetectorConfig, local_z  # noqa: E402
from landers.strip import Strip  # noqa: E402


def comps_near(mask, z, r, c, radius):
    lab, n = ndimage.label(mask)
    out = []
    if n == 0:
        return out
    idx = np.arange(1, n + 1)
    areas = ndimage.sum(np.ones_like(lab), lab, idx)
    cents = ndimage.center_of_mass(np.abs(z), lab, idx)
    peaks = ndimage.maximum(np.abs(z), lab, idx)
    for i in range(n):
        d = math.hypot(cents[i][0] - r, cents[i][1] - c)
        if d <= radius:
            out.append({"d_px": round(d, 1), "area": int(areas[i]), "peak_z": round(float(peaks[i]), 1)})
    return sorted(out, key=lambda x: x["d_px"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--window", type=int, default=512)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    cfg = DetectorConfig()
    key = json.loads(Path(a.answers).read_text())
    strips: dict = {}
    rows = []
    for site in key["sites"]:
        for pc in site["pieces"]:
            if pc.get("line") is None:
                continue
            sid = pc["strip"]
            if sid not in strips:
                strips[sid] = Strip.open(sid)
            strip = strips[sid]
            lbl = strip.label
            row, col = float(pc["line"]) - 1, float(pc["sample"]) - 1
            win = strip.read_centered(row, col, a.window)
            z = local_z(win.data, win.valid, cfg.background_px, cfg.smooth_sigma, cfg.inner_px)
            r, c = row - win.row0, col - win.col0
            drow, dcol = geo.shadow_direction(lbl)
            prof = []
            for t in range(-40, 41, 2):
                pr, pc_ = r + drow * t, c + dcol * t
                rr, cc = int(round(pr)), int(round(pc_))
                prof.append(round(float(z[rr - 1 : rr + 2, cc - 1 : cc + 2].mean()), 1))
            bright = comps_near(z > cfg.z_bright, z, r, c, 40)
            dark = comps_near(z < cfg.z_shadow_dark, z, r, c, 40)
            n_bright_100 = len(comps_near(z > cfg.z_bright, z, r, c, 100))
            rows.append(
                {
                    "site": site["name"],
                    "piece": pc["piece"],
                    "strip": sid,
                    "z_at": round(float(z[int(round(r)), int(round(c))]), 1),
                    "z_max_5px": round(float(z[int(r) - 5 : int(r) + 6, int(c) - 5 : int(c) + 6].max()), 1),
                    "z_min_5px": round(float(z[int(r) - 5 : int(r) + 6, int(c) - 5 : int(c) + 6].min()), 1),
                    "bright_within_40": bright[:6],
                    "dark_within_40": dark[:6],
                    "n_bright_within_100": n_bright_100,
                    "shadow_len_px_1m_3m": [
                        round(geo.shadow_length_px(lbl, 1.0), 1),
                        round(geo.shadow_length_px(lbl, 3.0), 1),
                    ],
                    "profile_sun_to_antisun_2px": prof,
                }
            )
            print(
                site["name"],
                pc["piece"],
                "z",
                rows[-1]["z_at"],
                "max",
                rows[-1]["z_max_5px"],
                "min",
                rows[-1]["z_min_5px"],
            )
            print("  bright", bright[:4])
            print("  dark", dark[:4])
            print("  n_bright_100", n_bright_100, "shadow 1-3 m px", rows[-1]["shadow_len_px_1m_3m"])
            print("  profile", prof)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rows, indent=1))
    print("written:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
