"""Item 14, drafting aid: the first votes of item 9c by what they sat on, to set the single-vote rule before any call.

    uv run experiments/vote_stats_9c.py

Reads docs/reports/2026-10-29-model-scoreboard (votes_*.json, summary.json). Writes out/deep14/vote_stats_9c.json.
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "docs/reports/2026-10-29-model-scoreboard"
THRESHOLDS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

summary = json.loads((PUB / "summary.json").read_text())


pieces = {(r["strip"], r["id"]) for r in summary["ids"] if r["on_piece"]}
first, later, tok_in, tok_out = {"piece": [], "fa": []}, {"piece": [], "fa": []}, [], []
for f in sorted(PUB.glob("votes_*.json")):
    sid = f.stem.removeprefix("votes_")
    for r in json.loads(f.read_text())["records"]:
        if "votes" not in r:
            continue
        side = "piece" if (sid, r["id"]) in pieces else "fa"
        for j, v in enumerate(r["votes"]):
            (first if j == 0 else later)[side].append((v["verdict"], v["confidence"]))
            tok_in.append(v["tokens"]["input"])
            tok_out.append(v["tokens"]["output"])


def table(votes):
    return {
        "n": len(votes),
        "verdicts": dict(Counter(v for v, _ in votes)),
        "natural_at_or_above": {str(t): sum(v == "natural" and c >= t for v, c in votes) for t in THRESHOLDS},
        "natural_confidences": sorted(c for v, c in votes if v == "natural"),
    }


out = {
    "source": "docs/reports/2026-10-29-model-scoreboard votes_*.json and summary.json",
    "n_piece_ids": len(pieces),
    "first_vote": {k: table(v) for k, v in first.items()},
    "later_votes": {k: table(v) for k, v in later.items()},
    "tokens_per_vote": {"n": len(tok_in), "input_mean": sum(tok_in) / len(tok_in), "output_mean": sum(tok_out) / len(tok_out),
                        "output_max": max(tok_out), "input_max": max(tok_in)},
}
path = ROOT / "out/deep14/vote_stats_9c.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
