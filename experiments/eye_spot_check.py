"""Scratch: is a spot a person flagged by eye in a candidates file, and where does it rank within a radius
of an anchor? Writes a JSON next to the sheets so a report can quote it. Not a result about the hardware.

    uv run experiments/eye_spot_check.py <candidates.json> <strip id> LINE,SAMPLE ANCHOR_LINE,ANCHOR_SAMPLE \
        --radius-m 1500 --match-m 10 --out out/.../eye_spot_check.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("strip")
    ap.add_argument("spot", help="LINE,SAMPLE (PDS, 1-based)")
    ap.add_argument("anchor", help="LINE,SAMPLE (PDS, 1-based)")
    ap.add_argument("--radius-m", type=float, default=1500.0)
    ap.add_argument("--match-m", type=float, default=10.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    run = json.loads(Path(a.candidates).read_text())
    entry = run["strips"][a.strip]
    scale = float(entry["scale_m"])
    sl, ss = (float(x) for x in a.spot.split(","))
    al, as_ = (float(x) for x in a.anchor.split(","))
    within = [
        c for c in entry["candidates"] if math.hypot(c["row"] - (al - 1), c["col"] - (as_ - 1)) * scale <= a.radius_m
    ]
    within.sort(key=lambda c: -c["score"])
    near = []
    for rank, c in enumerate(within, 1):
        d = math.hypot(c["row"] - (sl - 1), c["col"] - (ss - 1)) * scale
        if d <= a.match_m:
            near.append(
                {
                    "rank_within_radius": rank,
                    "line": round(c["row"] + 1, 1),
                    "sample": round(c["col"] + 1, 1),
                    "distance_m": round(d, 1),
                    "score": c["score"],
                    "branch": c["branch"],
                    "area_px": c.get("area_px"),
                    "extra": c.get("extra", {}),
                }
            )
    nearest = min(
        ((math.hypot(c["row"] - (sl - 1), c["col"] - (ss - 1)) * scale, i + 1, c) for i, c in enumerate(within)),
        default=None,
    )
    out = {
        "candidates_file": a.candidates,
        "git_commit": run.get("git_commit"),
        "strip": a.strip,
        "spot": {"line": sl, "sample": ss},
        "anchor": {"line": al, "sample": as_},
        "radius_m": a.radius_m,
        "match_m": a.match_m,
        "within_radius": len(within),
        "matches": near,
        "nearest_any": None
        if nearest is None
        else {
            "distance_m": round(nearest[0], 1),
            "rank_within_radius": nearest[1],
            "branch": nearest[2]["branch"],
            "score": nearest[2]["score"],
        },
    }
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
