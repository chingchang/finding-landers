"""Score a detector run against the tuning answer key.

    uv run scripts/score.py out/candidates_<run>.json
    uv run scripts/score.py out/candidates_<run>.json --heldout     # a person, once, detector frozen

Reads controls/thresholds.json (owned by a person; see docs/proposals/ for proposed values) and
controls/tuning.json. With --heldout it reads controls/heldout.json instead, and only if the run's
detector config carries "frozen": true. Writes out/score_<run>.json and prints the report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.score import format_report, load_json, score  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--answers", default=None, help="answer key (default controls/tuning.json)")
    ap.add_argument("--heldout", action="store_true", help="score the sealed held-out sites (person only)")
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out"))
    a = ap.parse_args(argv)

    if not Path(a.thresholds).exists():
        print(
            f"no thresholds file at {a.thresholds}. A person creates it; proposals live in docs/proposals/.",
            file=sys.stderr,
        )
        return 2
    cands = load_json(a.candidates)
    answers_path = a.answers or str(config.REPO_ROOT / "controls" / ("heldout.json" if a.heldout else "tuning.json"))
    if a.heldout:
        if not cands.get("detector", {}).get("frozen"):
            print("refusing --heldout: the run's detector config is not marked frozen", file=sys.stderr)
            return 3
        print("HELD-OUT EVALUATION: this run counts once. Reading the sealed answer key.", file=sys.stderr)
    s = score(cands, load_json(answers_path), load_json(a.thresholds))
    run = cands.get("run") or Path(a.candidates).stem.replace("candidates_", "")
    out = Path(a.out) / f"score_{run}{'_heldout' if a.heldout else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(s.to_json())
    print(format_report(s))
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
