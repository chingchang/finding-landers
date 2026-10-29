"""Apply a shape rules file to a candidates file whose candidates carry recorded shape features.

    uv run scripts/rescore.py out/candidates_<run>.json landers/shape_v1.json

Writes ``candidates_<run>_<rules version>.json`` beside the input: the same candidates, each passing
candidate's score raised by the rule gains (landers/shape.py), the detector config marked with the rules
file. The result is what ``scripts/detect.py --shape-rules`` would have written from the same pixels, so a
rules change can be scored without a day of detection. Nothing is dropped and no position changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.shape import ShapeRules, apply_rules_json  # noqa: E402


def repo_relative(path: str) -> str:
    p = Path(path).resolve()
    return str(p.relative_to(config.REPO_ROOT)) if p.is_relative_to(config.REPO_ROOT) else path


def rescore(run: dict, rules: ShapeRules, rules_path: str) -> dict:
    if run.get("detector", {}).get("shape_rules"):
        raise ValueError(f"run already carries shape rules {run['detector']['shape_rules']}; rescore the unruled run")
    out = dict(run)
    out["detector"] = {**run.get("detector", {}), "shape_rules": repo_relative(rules_path)}
    out["run"] = f"{run.get('run', 'run')}_{rules.version}"
    out["rescored_from"] = run.get("run")
    strips = {}
    n_pass = 0
    for sid, entry in run.get("strips", {}).items():
        cands = [apply_rules_json(c, rules) for c in entry.get("candidates", [])]
        n_pass += sum(1 for c in cands if (c.get("extra") or {}).get("shape_pass"))
        strips[sid] = {**entry, "candidates": cands}
    out["strips"] = strips
    out["shape_rules_passed"] = n_pass
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("rules")
    ap.add_argument("--out", default=None, help="output path (default: beside the input)")
    a = ap.parse_args(argv)
    run = json.loads(Path(a.candidates).read_text())
    rules = ShapeRules.load(a.rules)
    out = rescore(run, rules, a.rules)
    path = Path(a.out) if a.out else Path(a.candidates).with_name(f"candidates_{out['run']}.json")
    path.write_text(json.dumps(out, indent=1))
    print(f"{out['shape_rules_passed']} candidates passed at least one rule; written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
