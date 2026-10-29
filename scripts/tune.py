"""Judge one tuning-loop change against both scoreboards and the bar of docs/plan.md item 8.

    uv run scripts/tune.py --name sat5 --rules experiments/rules/sat5.json
    uv run scripts/tune.py --name ref                      # the reference rules against no rules at all

The candidate rules file needs only the tests (name, branches, conditions); the pass fraction and gain of
every rule are measured on the key run's false alarms before scoring (landers/tune.py). Both boards are
rescored from recorded features, nothing is re-detected: the key board from an unruled candidates file of
the tuning strips, the injection board from an unruled transplant run whose detections carry features.
After a detector change, point --key-candidates and --injection at the new runs and add --refit-reference.

Writes out/tune/<name>/tune_<name>.json (both boards, the checks, the fitted rules) and prints the tables.
A KEEP is a proposal for a person; nothing here edits landers/shape_v*.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.score import load_json  # noqa: E402
from landers.shape import ShapeRules  # noqa: E402
from landers.tune import compare, format_compare  # noqa: E402

_RULE_FILES = sorted((config.REPO_ROOT / "landers").glob("shape_v*.json"))
DEFAULT_REFERENCE = _RULE_FILES[-1] if _RULE_FILES else None
# detector v0.3 runs (same candidates as the v0.2 runs out/shape_v1/candidates_v02b_features.json and
# out/transplant_t2, plus features on the dark branch and tile_count)
DEFAULT_KEY = config.REPO_ROOT / "out" / "shape_v3" / "candidates_v03_features.json"
DEFAULT_INJECTION = config.REPO_ROOT / "out" / "transplant_t4" / "transplant_t4.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--rules", default=None, help="candidate rules JSON; omitted: judge the reference against none")
    ap.add_argument("--reference-rules", default=str(DEFAULT_REFERENCE) if DEFAULT_REFERENCE else None)
    ap.add_argument("--no-reference-rules", action="store_true")
    ap.add_argument("--key-candidates", default=str(DEFAULT_KEY), help="unruled candidates file, tuning strips")
    ap.add_argument("--injection", default=str(DEFAULT_INJECTION), help="unruled transplant run with features")
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--refit-reference", action="store_true", help="re-measure the reference's gains too")
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out" / "tune"))
    a = ap.parse_args(argv)

    for p in (a.key_candidates, a.injection):
        if not Path(p).exists():
            print(f"missing: {p}", file=sys.stderr)
            return 2
    reference = None if a.no_reference_rules or not a.reference_rules else ShapeRules.load(a.reference_rules)
    candidate = ShapeRules.load(a.rules) if a.rules else None
    r = compare(
        a.name,
        load_json(a.key_candidates),
        load_json(a.answers),
        load_json(a.thresholds),
        load_json(a.injection),
        reference,
        candidate,
        refit_reference=a.refit_reference,
    )
    r["inputs"] = {
        "key_candidates": a.key_candidates,
        "injection": a.injection,
        "reference_rules": None if reference is None else a.reference_rules,
        "candidate_rules": a.rules,
        "answers": a.answers,
        "thresholds": a.thresholds,
    }
    out_dir = Path(a.out) / a.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"tune_{a.name}.json"
    out.write_text(json.dumps(r, indent=1))
    if r["candidate_rules"] is not None:
        (out_dir / f"{a.name}_fitted_rules.json").write_text(json.dumps(r["candidate_rules"], indent=1))
    print(format_compare(r))
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
