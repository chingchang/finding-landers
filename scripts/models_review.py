"""Muse Spark review of one strip's evidence: candidates plus the SAM and vote records, through the five
tools; verdicts keep or lower, each citing evidence; the tool log beside the result.

    uv run scripts/models_review.py <candidates.json> --strip <id> --backend fake
    uv run scripts/models_review.py <candidates.json> --strip <id> --backend dry-run --max-turns 8

Reads out/models/sam_<strip>.json and votes_<strip>.json when present. The bounded checks Spark may order
(zoom pass, more votes, second-date check) run through the same ledger. Writes out/models/review_<strip>.json
with verdicts, grades before and after, the final answer and the tool log. The strip is called "strip_a"
inside the prompt; the mapping lives in this file's output only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.models import run, spark  # noqa: E402
from landers.score import load_json  # noqa: E402
from landers.strip import Strip  # noqa: E402
from scripts.models_sam import BACKENDS, strip_reader  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--strip", required=True)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--backend", choices=BACKENDS, default="fake")
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--max-turns", type=int, default=spark.MAX_TURNS)
    ap.add_argument("--no-checks", action="store_true", help="refuse every request_check")
    ap.add_argument("--out-dir", default="out/models")
    a = ap.parse_args(argv)

    data = load_json(a.candidates)
    if a.strip not in data["strips"]:
        print(f"{a.strip}: not in this run", file=sys.stderr)
        return 2
    cands = run.top_candidates(data["strips"][a.strip]["candidates"], a.top)
    out = Path(a.out_dir)
    sam_recs = load_json(out / f"sam_{a.strip}.json")["records"] if (out / f"sam_{a.strip}.json").exists() else None
    votes = load_json(out / f"votes_{a.strip}.json")["records"] if (out / f"votes_{a.strip}.json").exists() else None
    thresholds = load_json(a.thresholds) if Path(a.thresholds).exists() else {}
    client = run.open_client(a.backend, out)
    checks = None
    if not a.no_checks:
        strip = Strip.open(a.strip)
        checks = run.check_runner(client, strip_reader(strip), cands, strip.label.scale_m)
    store = run.build_store(cands, thresholds, "strip_a", sam_recs, votes, checks)
    print(f"backend {client.backend.name}; spark remaining {client.ledger.remaining('spark')}")
    print(f"{len(store.records)} evidence records")
    res = spark.review(client, store, "strip_a", a.max_turns)
    result = res.to_json()
    result["strip"] = a.strip
    result["ids"] = {run.candidate_id(i): {"row": c["row"], "col": c["col"]} for i, c in enumerate(cands)}
    result["checks"] = store.check_log
    result["reasoning"] = res.reasoning  # logged, not shown on the board
    run.write_json(out / f"review_{a.strip}.json", result)
    lowered = sum(1 for g in res.grades.values() if g["after"] != g["before"])
    print(f"{res.stopped} after {res.turns} turns; {len(res.verdicts)} verdicts, {lowered} lowered")
    print(f"cost so far ${client.ledger.total_cost_usd()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
