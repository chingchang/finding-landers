"""Fit the common score scale from injection runs and write it as JSON.

    uv run scripts/calibrate.py out/inject_fitA.json out/inject_fitB.json --version v0 --out landers/calibration_v0.json

Inputs must be outputs of scripts/inject.py (they carry raw detections and truths). Use runs from one
tile phase to fit and the other phase to evaluate, so recall is never measured on the tiles it was fitted on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import calibrate  # noqa: E402
from landers.score import load_json  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    runs = [load_json(p) for p in a.runs]
    for p, r in zip(a.runs, runs, strict=True):
        if "detections" not in r or "truths" not in r:
            print(f"{p}: not an injection run with raw detections", file=sys.stderr)
            return 2
    cal = calibrate.fit(runs, a.version)
    cal.save(a.out)
    print(f"fitted on {cal.area_km2:.3f} km2, {cal.n_tiles} tiles, sites {', '.join(cal.sites)}")
    for b, c in sorted(cal.branches.items()):
        print(
            f"  {b:13s} n_false={c.n:4d} raw top={c.scores[0]:.2f} (log10 rate {c.log_rates[0]:+.2f}) "
            f"raw bottom={c.scores[-1]:.2f} (log10 rate {c.log_rates[-1]:+.2f}) slope={c.slope:+.3f}"
        )
    print(f"written: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
