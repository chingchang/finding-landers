"""Where each recorded piece sits in every feature's false-alarm distribution on its own strip, and, with
a rules file, what fraction of false alarms each rule lets through (landers/features_eval.py).

    uv run scripts/feature_percentiles.py out/candidates_<run>.json --out out/<run>_features.json
    uv run scripts/feature_percentiles.py out/candidates_<run>.json --rules landers/shape_v1.json \\
        --out out/<run>_rules.json

Reads controls/tuning.json and controls/thresholds.json (the match radius). Writes one JSON; with
``--rules`` it also writes ``<out stem>_fitted_rules.json``, the rules with the measured false-alarm pass
fraction and gain filled in, for a person or the agent to copy into landers/shape_v<n>.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.features_eval import format_pieces, format_rules, measure  # noqa: E402
from landers.score import load_json  # noqa: E402
from landers.shape import ShapeRules  # noqa: E402

DEFAULT_COLUMNS = (
    "two_sided",
    "anti_sun_min_z",
    "sun_min_z",
    "shadow_height_m",
    "isolation_px",
    "saturated_px",
    "edge_sharpness",
    "tile_rank",
    "elongation",
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--rules", default=None)
    ap.add_argument("--columns", default=",".join(DEFAULT_COLUMNS))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    rules = ShapeRules.load(a.rules) if a.rules else None
    m = measure(load_json(a.candidates), load_json(a.answers), load_json(a.thresholds), rules)
    m["candidates_file"] = a.candidates
    m["answers_file"] = a.answers
    m["thresholds_file"] = a.thresholds
    m["rules_file"] = a.rules
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, indent=1))
    print("value(fraction of same-branch false alarms on the strip >= value / <= value)")
    print(format_pieces(m, tuple(a.columns.split(","))))
    if rules is not None:
        print()
        print(format_rules(m))
        fitted = out.with_name(out.stem + "_fitted_rules.json")
        fitted.write_text(json.dumps(m["rules"]["fitted_rules"], indent=1))
        print(f"\nfitted rules written: {fitted}")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
