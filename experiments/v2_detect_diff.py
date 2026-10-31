"""Item 16a: a fresh frozen-v1 detection of a whole strip against the list item 13 took it from, by position and branch, so
one extra row does not read as every row below it moving. Scores only; no key.

    uv run experiments/v2_detect_diff.py out/v2/prove/strips/ID/detect.json ID out/shape_v3/candidates_v03_features.json --rules landers/shape_v3.json
    uv run experiments/v2_detect_diff.py out/v2/prove/strips/ID/detect.json ID out/heldout_v1/candidates_heldout_v1.json

Writes docs/reports/2026-10-31-v2-assembled/detect_diff_ID.json.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.shape import ShapeRules, apply_rules_json  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("detect")
ap.add_argument("strip")
ap.add_argument("source")
ap.add_argument("--rules", default=None, help="rules the source list had applied afterwards, as the export did")
a = ap.parse_args()

fresh = json.loads(Path(a.detect).read_text())["candidates"]
d = json.loads(Path(a.source).read_text())
rules = ShapeRules.load(a.rules) if a.rules else None
old = d["strips"][a.strip]["candidates"]
old = [apply_rules_json(c, rules) for c in old] if rules else old


def key(c):
    return c["row"], c["col"], c["branch"]


def brief(c, rank):
    return {"row": c["row"], "col": c["col"], "branch": c["branch"], "score": c["score"], "rank_in_its_list": rank[key(c)]}


fresh_rank = {key(c): i + 1 for i, c in enumerate(sorted(fresh, key=lambda c: -c["score"]))}
old_rank = {key(c): i + 1 for i, c in enumerate(sorted(old, key=lambda c: -c["score"]))}
x, y = {key(c): c for c in fresh}, {key(c): c for c in old}
both = x.keys() & y.keys()
order_x = [k for k in map(key, sorted(fresh, key=lambda c: -c["score"])) if k in both]
order_y = [k for k in map(key, sorted(old, key=lambda c: -c["score"])) if k in both]
res = {
    "what": "item 16a: fresh frozen-v1 detection against the list item 13 took, compared on row, col and branch",
    "source": a.source,
    "source_detector_version": d["detector"].get("version"),
    "source_commit": d.get("git_commit"),
    "rules_applied_afterwards": a.rules,
    "fresh": len(fresh),
    "source_rows": len(old),
    "in_both": len(both),
    "in_both_with_another_score": sum(x[k]["score"] != y[k]["score"] for k in both),
    "in_both_with_another_raw_score": sum(x[k]["extra"]["raw_score"] != y[k]["extra"]["raw_score"] for k in both),
    "in_both_same_order": order_x == order_y,
    "only_fresh": sorted((brief(x[k], fresh_rank) for k in x.keys() - y.keys()), key=lambda r: r["rank_in_its_list"]),
    "only_source": sorted((brief(y[k], old_rank) for k in y.keys() - x.keys()), key=lambda r: r["rank_in_its_list"]),
}
out = config.REPO_ROOT / "docs" / "reports" / "2026-10-31-v2-assembled" / f"detect_diff_{a.strip}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res, indent=1))
print({k: v for k, v in res.items() if not k.startswith("only_")}, len(res["only_fresh"]), len(res["only_source"]))
