"""Item 15a's check and summary: each input list read again beside its copy with the column, apart from the runner.

    uv run experiments/halfcal_column_check.py LIST.json ...

Writes docs/reports/2026-10-30-halfcal-column/summary.json. Exits 1 if any row differs other than by the column.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from landers.halfcal import BELOW_FIELD, RATE_FIELD  # noqa: E402

COPIES = ROOT / "out" / "halfcal" / "column"
OUT = ROOT / "docs" / "reports" / "2026-10-30-halfcal-column" / "summary.json"
TOP = 20


def order(rows: list[dict]) -> list[tuple]:
    return [(c["row"], c["col"], c["branch"], c["score"]) for c in sorted(rows, key=lambda c: -c["score"])]


def main() -> int:
    runner = json.loads((COPIES / "summary.json").read_text())
    res = {"git": runner["git"], "lists": {}, "strips": {}}
    bad = 0
    for path in map(Path, sys.argv[1:]):
        before = json.loads(path.read_text())
        after = json.loads((COPIES / path.name).read_text())
        for sid, entry in before["strips"].items():
            a = after["strips"][sid]["candidates"]
            b = entry["candidates"]
            same_fields = b == [{k: v for k, v in c.items() if k not in (RATE_FIELD, BELOW_FIELD)} for c in a]
            same_order = order(b) == order(a)
            one_of_two = all((c[RATE_FIELD] is None) != (c[BELOW_FIELD] is None) for c in a)
            bad += not (same_fields and same_order and one_of_two)
            top = sorted(a, key=lambda c: -c["score"])[:TOP]
            rec = runner["lists"][path.name][sid]
            res["strips"][f"{path.name}/{sid}"] = {
                "rows": len(a),
                "same_fields": same_fields,
                "same_order": same_order,
                "one_of_two_fields": one_of_two,
                "rows_at_cap": sum(c[RATE_FIELD] is None for c in a),
                "at_cap_in_top_20_by_score": sum(c[RATE_FIELD] is None for c in top),
                "population": rec["population"],
                "population_at_cap": rec["population_at_cap"],
                "checked_against_item_15": rec["checked_against_item_15"],
                "area_km2_by_colour": rec["area_km2_by_colour"],
                "rate_per_km2_min_median_max": rec["rate_per_km2_min_median_max"],
            }
        digest = hashlib.sha256((COPIES / path.name).read_bytes()).hexdigest()
        res["lists"][path.name] = {"strips": len(before["strips"]), "sha256": digest}
    s = list(res["strips"].values())
    res["totals"] = {
        "lists": len(res["lists"]),
        "strip_lists": len(s),
        "rows": sum(x["rows"] for x in s),
        "rows_differing": bad,
        "at_cap_rows": sum(x["rows_at_cap"] for x in s),
        "checked_against_item_15": sum(x["checked_against_item_15"] for x in s),
        "at_cap_in_top_20_min_max": [
            min(x["at_cap_in_top_20_by_score"] for x in s),
            max(x["at_cap_in_top_20_by_score"] for x in s),
        ],
        "top_20_rows_shown": sum(min(TOP, x["rows"]) for x in s),
        "at_cap_in_top_20_rows": sum(x["at_cap_in_top_20_by_score"] for x in s),
        "population_at_cap_min_max": [min(x["population_at_cap"] for x in s), max(x["population_at_cap"] for x in s)],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res["totals"], indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
