"""Item 14's price, from the ledgers and item 9c's votes, no model call.

    uv run experiments/deep14_price.py --dry out/deep14_dry

Reads docs/reports/ledgers.json, docs/reports/2026-10-29-model-scoreboard/, out/deep14/vote_stats_9c.json, and the dry run's
counts. Writes out/deep14/price.json.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers.models.ledger import PRICES_USD, TOTAL_CAP_USD, spent_usd  # noqa: E402
from landers.models.wonder import SingleVoteRule  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "docs/reports/2026-10-29-model-scoreboard"
CHECKS_PER_STRIP, VOTES_PER_CHECK, REVIEW_TURNS = 3, 3, 6
UNDERCOUNT = 2.0  # what if the bill is this many times the ledger's Wonder estimate; a stress test, not a measurement


def load(path):
    return json.loads(Path(path).read_text())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", required=True)
    a = ap.parse_args()
    dry = Path(a.dry)
    stats = load(ROOT / "out/deep14/vote_stats_9c.json")
    ledgers = [{"item": r["item"], "path": r["path"], "usd": load(ROOT / r["path"])["total_cost_usd"]} for r in load(ROOT / "docs/reports/ledgers.json")["ledgers"] if (ROOT / r["path"]).exists()]
    spent = spent_usd()
    led9c = load(PUB / "ledger.json")["entries"]

    w = PRICES_USD["wonder"]
    tok = stats["tokens_per_vote"]
    per_vote = tok["input_mean"] * w["input_token"] + tok["output_mean"] * w["output_token"]
    first_all = stats["first_vote"]["piece"]["n"] + stats["first_vote"]["fa"]["n"]
    rule = SingleVoteRule()
    confidences = stats["first_vote"]["piece"]["natural_confidences"] + stats["first_vote"]["fa"]["natural_confidences"]
    band = sum(rule.band_low <= c < rule.lower_alone for c in confidences)
    band_share = band / first_all
    votes_per_candidate = 1 + 2 * band_share
    per_turn = led9c["spark"]["cost_usd"] / led9c["spark"]["units"]

    strips = len(load(ROOT / "out/deep14/inputs/candidates_combined.json")["strips"])
    transplant = load(ROOT / "out/deep14/inputs/transplant_votes.json")["n"]
    probe_calls = 18
    rows = []
    for top in (50, 100, 150, 200):
        votes = strips * top * votes_per_candidate
        tp_votes = transplant * votes_per_candidate
        checks = strips * CHECKS_PER_STRIP * VOTES_PER_CHECK
        turns = strips * REVIEW_TURNS
        item = (votes + tp_votes + probe_calls) * per_vote
        review = checks * per_vote + turns * per_turn
        rows.append({"top_per_strip": top, "candidates": strips * top, "wonder_calls": round(votes + tp_votes + probe_calls + checks),
                     "votes_and_probe_usd": round(item, 2), "spark_and_check_votes_usd": round(review, 2), "total_usd": round(item + review, 2),
                     "all_three_votes_usd": round((strips * top * 3 + transplant * 3 + probe_calls) * per_vote + review, 2),
                     "if_wonder_bill_is_double_usd": round(UNDERCOUNT * (item + checks * per_vote) + turns * per_turn, 2),
                     "all_runs_after_usd": round(spent + item + review, 2)})
    out = {
        "cumulative": {"ledgers": ledgers, "total_usd": spent, "cap_usd": TOTAL_CAP_USD},
        "per_wonder_vote_usd": round(per_vote, 5),
        "tokens_per_vote_9c": tok,
        "first_votes_9c": first_all,
        "first_votes_in_band_9c": band,
        "band_share_9c": round(band_share, 3),
        "votes_per_candidate": round(votes_per_candidate, 3),
        "spark_usd_per_turn_9c": round(per_turn, 4),
        "strips": strips,
        "transplant_vote_set": transplant,
        "probe_calls": probe_calls,
        "checks_per_strip": CHECKS_PER_STRIP,
        "review_turns": REVIEW_TURNS,
        "rows": rows,
        "dry_run": {"ledger": load(dry / "ledger.json")["entries"], "requests_written": sum(1 for _ in (dry / "model_requests").iterdir())},
    }
    path = ROOT / "out/deep14/price.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "dry_run"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
