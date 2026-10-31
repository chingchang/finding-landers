"""Item 16a: print the proof files' numbers for the report, and write the search's commands in plan order."""

import json
from pathlib import Path

R = Path("docs/reports/2026-10-31-v2-assembled")
d = json.loads((R / "proof.json").read_text())
print("git", d["git"])
for k, v in d["strips"].items():
    x = v["detection_against_item_13"]
    print(k, "|", x["item_13_took_it_from"]["file"], x["candidates"], x["candidates_in_item_13"], "same-rank-diff", x["rows_at_the_same_rank_differing"], "only here", len(x["top_2000_only_here"]), "only 13", len(x["top_2000_only_in_item_13"]), "both", x["top_2000_in_both"], "other", x["in_both_with_another_value"])
    print("  ", v["against_item_13_combined"], v["against_item_15a_column"], v["fake_stage"], v["dry_run_requests"], v["key_ranks_differing_from_item_14"], len(v["key_ranks"]))
    print("  off", v["files_read_stage_off"][:30])
    print("  fake", [f for f in v["files_read_stage_fake"] if "hf/" not in f][:30])
    print("  ranks only here", [(r["rank"], r["branch"], r["score"]) for r in x["top_2000_only_here"]])
    print("  ranks only 13", [(r["rank"], r["branch"], r["score"]) for r in x["top_2000_only_in_item_13"]])
u = json.loads((R / "unseen.json").read_text())
print({k: v for k, v in u.items() if k != "files_read"})
print("unseen files", [f for f in u["files_read"] if "hf/" not in f], "hf files", sum("hf/" in f for f in u["files_read"]))
f = json.loads((R / "freeze.json").read_text())
print(f["git"], f["model"], f["numbers_in_code"], {k: v for k, v in f["sha256"].items() if not k.endswith(".py")}, len(f["sha256"]))
for path in sorted(R.glob("detect_diff_*.json")):
    x = json.loads(path.read_text())
    print(path.name, {k: v for k, v in x.items() if not k.startswith("only_")}, len(x["only_fresh"]), len(x["only_source"]))
plan = json.loads(Path("out/search/plan.json").read_text())["strips"]
ids = [s["observation_id"] for s in plan]
lines = [
    "# Item 17's search pass, in the plan's order (2007 PSP strips first), one strip per command so each lands on its own.",
    "# Detection comes from frozen-v1's search lists, which the same detector wrote.",
    "# These lines assume the model stage is off in landers/v2.json. With it on, each needs a --backend and votes as it goes; run only the last line.",
]
for sid in ids:
    lines.append(f"uv run --group rerank --env-file out/landers.env scripts/v2.py {sid} --out out/v2/search --detections {sid}=out/search/candidates/candidates_{sid}.json")
every = " ".join(ids)
pairs = " ".join(f"{sid}=out/search/candidates/candidates_{sid}.json" for sid in ids)
lines += [
    "# The whole list, from the strips written above, then any model stage: one command, so the votes go rank by rank across every strip.",
    f"uv run --group rerank --env-file out/landers.env scripts/v2.py {every} --out out/v2/search --detections {pairs}",
]
(R / "search_commands.txt").write_text("\n".join(lines) + "\n")
print(len(ids), ids[:3], Path(f"out/search/candidates/candidates_{ids[0]}.json").exists(), all(Path(f"out/search/candidates/candidates_{i}.json").exists() for i in ids))
