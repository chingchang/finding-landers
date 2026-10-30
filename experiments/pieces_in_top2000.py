"""Would the exported top 2,000 hold the recorded pieces? For every piece of controls/tuning.json, the best rank of a
candidate within the piece's match radius, in the same list the export ranked. Each piece is looked up alone, so
a candidate may serve two pieces here, which scoring does not allow; this asks what the crops hold, it is not a
score. Numbers on the four sites sealed for frozen-v1 are not blind. Output out/export/pieces_in_top2000.json.

    uv run --env-file out/landers.env experiments/pieces_in_top2000.py
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import search_export as se  # noqa: E402

from landers.shape import ShapeRules, apply_rules_json  # noqa: E402

TOP = 2000
pieces, _ = se.piece_sites()
_, thresholds = se.controls()
by_strip: dict = {}
for p in pieces:
    by_strip.setdefault(p["strip"], []).append(p)
rows = []
for path, rules_path in se.TUNING_LISTS:
    d = se.load(path)
    rules = ShapeRules.load(rules_path) if rules_path else None
    for sid in sorted(set(d["strips"]) & set(by_strip)):
        e = d["strips"][sid]
        cands = [apply_rules_json(c, rules) for c in e["candidates"]] if rules else e["candidates"]
        ranked = sorted(cands, key=lambda c: -float(c["score"]))
        for p in by_strip[sid]:
            radius_m = thresholds["match_radius_m_by_kind"].get(p["kind"], thresholds["match_radius_m"])
            radius = radius_m / e["scale_m"]
            best = next((i + 1 for i, c in enumerate(ranked) if math.hypot(c["row"] - p["row"], c["col"] - p["col"]) <= radius), None)
            rows.append({"strip": sid, "site": p["site"], "piece": p["piece"], "kind": p["kind"], "best_rank": best,
                         "candidates_on_strip": len(ranked), "in_top": best is not None and best <= TOP})
    del d
summary = {k: dict(Counter("in top 2000" if r["in_top"] else ("listed below 2000" if r["best_rank"] else "never listed") for r in rows if r["kind"] == k))
           for k in sorted({r["kind"] for r in rows})}
out = {"what": __doc__.split("\n\n")[0], "n": len(rows), "summary": summary, "pieces": rows}
Path("out/export/pieces_in_top2000.json").write_text(json.dumps(out, indent=1))
print(json.dumps(summary))
for r in rows:
    if not r["in_top"]:
        print(r["strip"], r["kind"], r["best_rank"], r["candidates_on_strip"])
