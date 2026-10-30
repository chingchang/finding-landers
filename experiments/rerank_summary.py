"""The item 13 tables, from out/rerank/fit/*.json and out/rerank/controls/, into one file the report copies from.

    uv run experiments/rerank_summary.py

Output out/rerank/summary.json.
"""

import json
from pathlib import Path

ROOT = Path("out/rerank")
NS = ("N10", "N20", "N50", "N100", "N250", "board_rate")


def board(tp: dict) -> dict:
    return {k: {"found": tp[k]["found"], "n": tp[k]["n"], "interval_95": tp[k]["interval_95"]} for k in NS}


variants = ["primary", "no_score", "no_novelty", "embedding_only", "no_transplanted"]
fits = {v: json.loads((ROOT / "fit" / f"{v}.json").read_text()) for v in variants}
p = fits["primary"]
f = p["frozen_v1"]
out = {
    "protocol": p["protocol"], "encoder": p["encoder"], "git": p["git"], "rows": p["rows"], "planted_km2": p["planted_km2"],
    "median_target_km2": p["median_target_km2"], "target_strip_km2": p["target_strip_km2"], "rates_per_km2": p["rates_per_km2"], "no_texture": p["no_texture"],
    "run": {k: v for k, v in json.loads((ROOT / "t10" / "run.json").read_text()).items() if k in ("asked", "n_placements", "n_sham_placements", "n_detections", "area_km2", "skipped", "seed", "git")},
    "frozen_v1": {"key_curve": f["key_curve"], "key_kinds": f["key_kinds"], "key_by_site": f["key_by_site"], "key_spread_at_20": f["key_spread_at_20"], "key_interval_95_at_20": p["frozen_key_interval_95_at_20"],
                  "transplant": board(f["transplant"]), "transplant_N20": f["transplant"]["N20"], "transplant_spread_at_20": f["transplant_spread_at_20"]},
    "variants": {v: {"key_curve": x["key_curve"], "key_n": x["key_n"], "key_interval_95_at_20": x["key_interval_95_at_20"], "transplant": board(x["transplant"]), "dropped_from_top_20": x["dropped_from_top_20"], "paste": x["paste"],
                     "rule": x["rule"], "key_spread_at_20": x["key_spread_at_20"], "transplant_spread_at_20": x["transplant_spread_at_20"]} for v, x in fits.items()},
    "primary": {"key_kinds": p["key_kinds"], "key_by_site": p["key_by_site"], "transplant_N20": p["transplant"]["N20"], "auc_real_over_sham": p["auc_real_over_sham"], "auc_sham_over_tile_fa": p["auc_sham_over_tile_fa"]},
    "pieces": [{"piece": k, "frozen_v1": f["key_ranks"][k], "primary": p["key_ranks"].get(k), "no_transplanted": fits["no_transplanted"]["key_ranks"].get(k)} for k in sorted(f["key_ranks"])],
    "paste_rows": p["paste_rows"],
    "controls": {name: json.loads((ROOT / "controls" / f"{name}.json").read_text()) for name in ("repeat", "shuffle")},
}
fusion = json.loads((ROOT / "fusion.json").read_text())
out["fusion_exploratory"] = {"what": fusion["what"], "key_curve": fusion["key_curve"], "key_n": fusion["key_n"], "key_interval_95_at_20": fusion["key_interval_95_at_20"],
                             "dropped_from_top_20": fusion["dropped_from_top_20"], "transplant": board(fusion["transplant"]), "transplant_N20": fusion["transplant"]["N20"]}
(ROOT / "summary.json").write_text(json.dumps(out, indent=1))
print(json.dumps({k: out[k] for k in ("rows", "run", "rates_per_km2", "median_target_km2", "frozen_v1")}))
print(json.dumps(out["variants"]))
print(json.dumps(out["primary"]))
print(json.dumps(out["pieces"]))
print(json.dumps(out["paste_rows"]))
