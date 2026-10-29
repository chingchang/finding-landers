"""Leave-one-site-out check of a shape rules file against the item 8 bar (landers/loso.py).

    uv run scripts/loso.py --name shape_v2                       # the newest landers/shape_v*.json
    uv run scripts/loso.py --name e9 --rules experiments/rules/e9_all_three.json

For each tuning site, every rule is re-fitted on the other sites' false alarms (the key run without that
site's strips) and the site's pieces are scored under those gains; the six folds are pooled. Each rule is
then judged by ablation on the pooled held-out boards (key and injection). The rules file needs only the
tests; gains are measured per fold. Both boards are rescored from recorded features, nothing is re-detected.

Writes out/loso/<name>/loso_<name>.json and prints the tables. A rule that fails is a withdrawal to propose
to a person; nothing here edits landers/shape_v*.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.loso import format_loso, leave_one_site_out, tuning_site_strips  # noqa: E402
from landers.score import load_json  # noqa: E402
from landers.shape import ShapeRules  # noqa: E402

_RULE_FILES = sorted((config.REPO_ROOT / "landers").glob("shape_v*.json"))
DEFAULT_RULES = _RULE_FILES[-1] if _RULE_FILES else None
# detector v0.3 runs, as scripts/tune.py (same candidates as the v0.2 runs, plus dark-branch features)
DEFAULT_KEY = config.REPO_ROOT / "out" / "shape_v3" / "candidates_v03_features.json"
DEFAULT_INJECTION = config.REPO_ROOT / "out" / "transplant_t4" / "transplant_t4.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--rules", default=str(DEFAULT_RULES) if DEFAULT_RULES else None, help="rules JSON to check")
    ap.add_argument("--key-candidates", default=str(DEFAULT_KEY), help="unruled candidates file, tuning strips")
    ap.add_argument("--injection", default=str(DEFAULT_INJECTION), help="unruled transplant run with features")
    ap.add_argument("--no-injection", action="store_true", help="key board only")
    ap.add_argument("--answers", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out" / "loso"))
    a = ap.parse_args(argv)

    if not a.rules:
        print("no rules file", file=sys.stderr)
        return 2
    needed = [a.key_candidates] if a.no_injection else [a.key_candidates, a.injection]
    for p in needed:
        if not Path(p).exists():
            print(f"missing: {p}", file=sys.stderr)
            return 2
    r = leave_one_site_out(
        a.name,
        load_json(a.key_candidates),
        load_json(a.answers),
        load_json(a.thresholds),
        None if a.no_injection else load_json(a.injection),
        ShapeRules.load(a.rules),
        tuning_site_strips(load_json(a.sites)),
    )
    r["inputs"] = {
        "rules": a.rules,
        "key_candidates": a.key_candidates,
        "injection": None if a.no_injection else a.injection,
        "answers": a.answers,
        "thresholds": a.thresholds,
        "sites": a.sites,
    }
    out_dir = Path(a.out) / a.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"loso_{a.name}.json"
    out.write_text(json.dumps(r, indent=1))
    print(format_loso(r))
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
