"""Scratch: every candidate within a radius of a recorded piece in one or more runs, with its strip-wide rank,
so a change in a piece's rank can be read branch by branch. Reads the key; not part of the pipeline.

    uv run experiments/near_piece.py schiaparelli backshell --radius 60 \
        base=out/baseline_v1/candidates_baseline_v1.json v02=out/shape_v1/candidates_v02_features.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site")
    ap.add_argument("piece")
    ap.add_argument("runs", nargs="+", help="name=path of a candidates file")
    ap.add_argument("--radius", type=float, default=60.0, help="pixels")
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    a = ap.parse_args(argv)
    key = json.loads(Path(a.answers).read_text())
    pc = next(p for s in key["sites"] if s["name"] == a.site for p in s["pieces"] if p["piece"] == a.piece)
    row, col, sid = float(pc["line"]) - 1.0, float(pc["sample"]) - 1.0, pc["strip"]
    for spec in a.runs:
        name, path = spec.split("=", 1)
        run = json.loads(Path(path).read_text())
        cands = sorted(run["strips"][sid]["candidates"], key=lambda c: -float(c["score"]))
        print(f"== {name}: {a.site}/{a.piece} on {sid}, {len(cands)} candidates, within {a.radius:.0f} px")
        print(f"{'rank':>7s} {'d_px':>6s} {'drow':>6s} {'dcol':>6s} {'branch':12s} {'score':>7s} {'area':>6s}  extra")
        for i, c in enumerate(cands, start=1):
            dr, dc = float(c["row"]) - row, float(c["col"]) - col
            d = math.hypot(dr, dc)
            if d <= a.radius:
                extra = {k: v for k, v in (c.get("extra") or {}).items() if k != "also"}
                also = (c.get("extra") or {}).get("also")
                print(
                    f"{i:7d} {d:6.1f} {dr:6.1f} {dc:6.1f} {c['branch']:12s} {float(c['score']):7.2f} {c['area_px']:6d}  "
                    f"{json.dumps(extra)}{'  also=' + json.dumps(also) if also else ''}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
