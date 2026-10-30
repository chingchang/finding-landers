"""Item 12c(a) in one file, out/search/retry_summary.json: per retried pair, the coarse correlations, the nodes, the
round-trip closure in metres (the median offset A to B plus the median offset B to A, on the ground; zero when
the two directions agree), and seen against chance. Reads out/search/persist_12c/ and survivors_12c.json.

    uv run experiments/retry_summary.py
"""

import json
from pathlib import Path

root = Path("out/search")
inv = {s["observation_id"]: s for s in json.loads((root / "inventory.json").read_text())["strips"]}
scale = {k: v["scale_m"] for k, v in inv.items()}
s12 = json.loads((root / "survivors_12c.json").read_text())
s11 = json.loads((root / "survivors.json").read_text())
chance = {(c["from"], c["to"]): c for c in s12["chance"]["directions"]}
pairs = []
for f in sorted((root / "persist_12c").glob("persist_*.json")):
    d = json.loads(f.read_text())
    dirs = list(d["directions"].values())
    row = {"pair": d["pair"], "km2_shared": d["km2_shared"], "seconds": d["seconds"], "directions": []}
    for x in dirs:
        how = x["how"].get("coarse", {})
        row["directions"].append({"from": x["from"], "to": x["to"], "coarse_tried": how.get("tried"), "prior_px": x["how"].get("prior_px"),
                                  "registration": x["registration"], "counts": x["counts"], "chance": chance.get((x["from"], x["to"]))})
    a, b = dirs[0]["registration"], dirs[1]["registration"]
    if a.get("ok") and b.get("ok"):
        sa, sb = scale[dirs[0]["to"]], scale[dirs[1]["to"]]
        row["closure_m"] = [round(a["median_drow"] * sa + b["median_drow"] * sb, 2), round(a["median_dcol"] * sa + b["median_dcol"] * sb, 2)]
    pairs.append(row)
out = {
    "pairs": pairs,
    "registered_item_11": {k: s11["pairs"][k] for k in ("n", "registered", "km2_shared_all", "km2_shared_registered")},
    "registered_after_retry": {k: s12["pairs"][k] for k in ("n", "registered", "km2_shared_all", "km2_shared_registered")},
    "dates_seen_of_looked_item_11": s11["dates_seen_of_looked"],
    "dates_seen_of_looked_after_retry": s12["dates_seen_of_looked"],
    "chance_item_11": {k: s11["chance"][k] for k in ("looked", "seen", "expected_by_chance")},
    "chance_after_retry": {k: s12["chance"][k] for k in ("looked", "seen", "expected_by_chance")},
}
(root / "retry_summary.json").write_text(json.dumps(out, indent=1))
for p in pairs:
    print(p["pair"], p["km2_shared"], p.get("closure_m"))
    for x in p["directions"]:
        print("  ", x["from"], "->", x["to"], x["registration"], x["counts"], x["chance"], [(t["m_per_px"], t["median_corr"], t["max_corr"], t["spots_read"], t["spots_good"]) for t in x["coarse_tried"] or []])
print({k: v for k, v in out.items() if k != "pairs"})
check = json.loads(Path("out/export/check.json").read_text())
rows = check["strips"]
print("ok", check["ok"], "export bytes", check["export_bytes"], "delete", check["delete_proposed"]["bytes"], len(check["delete_proposed"]["strips"]), "free", check["free_gb_now"])
print("labels", check["labels"]["n"], check["labels"]["on_disk_not_copied"])
print("crops", sum(r["exported"] for r in rows), "expected", sum(r["expected"] for r in rows), "readback", sum(r["read_back"] for r in rows), "compared", sum(r["pixels_compared"] for r in rows), "equal", sum(r["pixels_equal"] for r in rows))
print("crop bytes", sum(r["bytes"] for r in rows))
print("windows", check["pieces"]["windows"], "replays", check["pieces"]["cut_replays_equal"], "shams not in t1", len(check["pieces"]["shams_differ_from_t1"]), "tiles", check["tiles"])
for g in check["nearest_targets"]:
    print(g)
