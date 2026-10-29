"""Scratch (item 8a): does a calibrated score mean the same false-alarm rate on every strip?

    uv run experiments/per_strip_rates.py out/shape_v4/candidates_v04_per_strip.json out/shape_v3/candidates_v03_features.json

For each candidates file and each strip, candidates per km2 above calibrated 0, 1 and 2 (nominal 1, 0.1 and
0.01 per km2 if the scale were honest), and the spread of those rates over the strips. The candidates are
nearly all false alarms, so this is the realised rate. Writes <first file's dir>/per_strip_rates.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LEVELS = (0.0, 1.0, 2.0)


def rates(run: dict) -> dict:
    out = {}
    for sid, e in run["strips"].items():
        area = float(e["valid_area_km2"])
        out[sid] = {str(lv): round(sum(1 for c in e["candidates"] if float(c["score"]) > lv) / area, 3) for lv in LEVELS}
    return out


def main(argv: list[str]) -> int:
    result = {}
    for p in argv:
        r = rates(json.loads(Path(p).read_text()))
        spread = {}
        for lv in LEVELS:
            v = [x[str(lv)] for x in r.values()]
            spread[str(lv)] = {"min": min(v), "max": max(v), "nominal": 10 ** (-lv)}
        result[p] = {"per_strip": r, "spread": spread}
        print(p)
        for sid, x in r.items():
            print(f"  {sid}: " + " ".join(f"{x[str(lv)]:8.3f}" for lv in LEVELS))
        print("  spread: " + "; ".join(f">{k}: {s['min']} to {s['max']} (nominal {s['nominal']})" for k, s in spread.items()))
    out = Path(argv[0]).parent / "per_strip_rates.json"
    out.write_text(json.dumps(result, indent=1))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
