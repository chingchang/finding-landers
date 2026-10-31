"""The committed copy of item 16's results and the tables the report copies, printed.

    uv run experiments/darkrelief_summary.py

Reads out/darkrelief/results.json. Output docs/reports/2026-10-30-darkrelief/summary.json.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "out" / "darkrelief" / "results.json").read_text())
arms = d["arms"]

print("rule", d["rule"], "git", d["git"], "allowed", d["false_alarms_allowed"], "sham", d["sham_at_N20"])
for name, a in arms.items():
    print(
        name, "key", a["key_curve"], "of", a["key_n"], "ci", a["key_interval_95_at_20"], "spread", a["key_spread_at_20"]
    )
    print(
        "   transplant",
        a["transplant_curve"],
        "ci",
        a["transplant"]["N20"]["interval_95"],
        "spread",
        a["transplant_spread_at_20"],
    )
    print("   kinds key", {k: v["20"] for k, v in a["key_kinds"].items()}, "tp N20", a["transplant"]["N20"]["by_kind"])
    print("   ground N20", a["transplant"]["N20"]["by_ground"])
    print("   dropped", a["dropped_from_top_20"], "rules", a.get("rules"))

print("\nfolds")
for site, r in d["folds"].items():
    print(site, r)

print("\nper strip")
for sid, r in d["per_strip"].items():
    print(sid, r)

print("\npiece candidates")
for r in sorted(d["piece_candidates"], key=lambda x: x["piece"]):
    print(r)

print("\npieces whose rank moved: frozen, loso, whole, flipped, recorded")
for k in sorted(arms["frozen_v1"]["key_ranks"]):
    row = [arms[a]["key_ranks"].get(k) for a in ("frozen_v1", "primary_loso", "whole_fit", "flipped", "recorded")]
    if len(set(row)) > 1:
        print(k, *row)

dest = ROOT / "docs" / "reports" / "2026-10-30-darkrelief" / "summary.json"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(d, indent=1))
print("\nwritten", dest, dest.stat().st_size)
