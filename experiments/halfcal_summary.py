"""The committed copy of item 15's results and the tables the report copies, printed.

    uv run experiments/halfcal_summary.py

Reads out/halfcal/results.json. Output docs/reports/2026-10-30-halfcal/summary.json.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "out" / "halfcal" / "results.json").read_text())
arms = d["arms"]

print("rule", d["rule"], "git", d["git"], "allowed", d["false_alarms_allowed"])
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
    print("   ground N20", a["transplant"]["N20"]["by_ground"], "board", a["transplant"]["board_rate"]["by_ground"])
    print("   kinds key", a["key_kinds"], "tp N20", a["transplant"]["N20"]["by_kind"])
print("dropped", {k: v.get("dropped_from_top_20") for k, v in arms.items() if k != "frozen_v1"})

print("\npieces: frozen, primary, shift, extrapolated, better_rank")
for k in sorted(arms["frozen_v1"]["key_ranks"]):
    print(k, *[arms[a]["key_ranks"].get(k) for a in ("frozen_v1", "primary", "shift", "extrapolated", "better_rank")])

for group, by_arm in d["check"].items():
    print("\ncheck", group)
    for arm, levels in by_arm.items():
        for lv, r in levels.items():
            print(arm, lv, {k: v for k, v in r.items() if k != "rows"})

print("\nmakeup")
for sid, m in d["top20_makeup"].items():
    print(sid, m)

dest = ROOT / "docs" / "reports" / "2026-10-30-halfcal" / "summary.json"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(d, indent=1))
print("\nwritten", dest, dest.stat().st_size)
