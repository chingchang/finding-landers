"""Scratch: per-piece ranks from several score files side by side, so a change can be read piece by piece.

    uv run experiments/rank_compare.py base=out/baseline_v1/score_baseline_v1.json \
        v02=out/shape_v1/score_v02_features.json rules=out/shape_v1/score_v02_features_shape_v1.json

Reads only what scripts/score.py wrote; changes nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    runs = {}
    for a in args:
        name, path = a.split("=", 1)
        runs[name] = json.loads(Path(path).read_text())
    names = list(runs)
    print(f"{'site':13s} {'piece':14s} " + " ".join(f"{n:>12s}" for n in names))
    first = runs[names[0]]
    for i, p in enumerate(first["pieces"]):
        cells = []
        for n in names:
            q = runs[n]["pieces"][i]
            assert (q["site"], q["piece"]) == (p["site"], p["piece"])
            cells.append("-" if q["rank"] is None else f"{q['rank']}/{q['branch'][:5]}")
        print(f"{p['site']:13s} {p['piece']:14s} " + " ".join(f"{c:>12s}" for c in cells))
    print()
    for n in names:
        s = runs[n]
        print(
            f"{n:8s} recall@{s['top_n']} = {s['recall_at_n']:.2f} ({s['n_pieces_found']}/{s['n_pieces_recorded']})  "
            f"median FA/km2 = {s['median_false_alarms_per_km2']:.2f}  {'PASS' if s['passed'] else 'FAIL'}"
        )
    print()
    print(f"{'strip':16s} " + " ".join(f"{n:>10s}" for n in names) + "   (false alarms per km2)")
    strips = [t["strip"] for t in first["strips"]]
    for sid in strips:
        cells = []
        for n in names:
            t = next((t for t in runs[n]["strips"] if t["strip"] == sid), None)
            cells.append("-" if t is None else f"{t['false_alarms_per_km2']:.1f}")
        print(f"{sid:16s} " + " ".join(f"{c:>10s}" for c in cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
