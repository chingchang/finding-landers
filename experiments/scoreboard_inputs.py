"""Inputs for the model-layer scoreboard (plan item 9c): the frozen-v1 key run with the adopted shape rules
applied, cut to the top ``--keep`` candidates of every strip so the model scripts need not load the full
candidate file each time.

    uv run experiments/scoreboard_inputs.py <candidates_v03_features.json> --out out/scoreboard/inputs

The rules are applied exactly as ``scripts/rescore.py`` and the tuning judge apply them
(``landers.shape.apply_rules_json``), then the candidates are sorted by the ruled score. Writes
``candidates_frozen_v1.json`` in the detector's own format; it stays under ``out/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.shape import ShapeRules, apply_rules_json  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--rules", default=str(config.REPO_ROOT / "landers" / "shape_v3.json"))
    ap.add_argument("--keep", type=int, default=200)
    ap.add_argument("--out", default="out/scoreboard/inputs")
    a = ap.parse_args(argv)

    data = json.loads(Path(a.candidates).read_text())
    if data.get("detector", {}).get("shape_rules"):
        raise SystemExit("input already carries shape rules; give the unruled run")
    rules = ShapeRules.load(a.rules)
    strips = {}
    for sid, s in data["strips"].items():
        ruled = [apply_rules_json(c, rules) for c in s["candidates"]]
        top = sorted(ruled, key=lambda c: -c["score"])[: a.keep]
        strips[sid] = {**{k: v for k, v in s.items() if k != "candidates"}, "candidates": top}
        grades = sorted({c.get("grade") for c in top})
        print(f"{sid}: kept {len(top)} of {len(s['candidates'])}; grades {grades}")
    head = {k: v for k, v in data.items() if k != "strips"}
    head["detector"] = {**head.get("detector", {}), "shape_rules": a.rules}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidates_frozen_v1.json").write_text(
        json.dumps({**head, "source": str(a.candidates), "strips": strips}, indent=1) + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
