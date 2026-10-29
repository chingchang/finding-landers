"""The case board: a static HTML page from results files only. No detector, no registration, no model call.

    uv run scripts/board.py out/<run>/candidates_<run>.json                 # persist_*.json beside it, out/models/
    uv run scripts/board.py <candidates.json> --models out/models --coverage out/search/coverage.json \\
        --score out/<run>/score_<run>.json --top 50 --out out/board/index.html
    uv run scripts/board.py <candidates.json> --blind --out out/board/blind.html   # strip ids and positions removed
    uv run scripts/board.py --demo out/board_demo                           # fake backend; files and page together

Writes the page and ``<page>_trace.json`` beside it: every value on the page with the file and JSON path it
was copied from. ``--blind`` runs the leak guard over the page and fails if anything identifying is left.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers.board import demo, load, render  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates", nargs="?")
    ap.add_argument("--models", default="out/models")
    ap.add_argument("--persist", nargs="*", default=None, help="persist_*.json files (default: beside the candidates)")
    ap.add_argument("--coverage", default="out/search/coverage.json")
    ap.add_argument("--score", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--blind", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--demo", default=None, metavar="DIR", help="write demo results files to DIR and build from them")
    a = ap.parse_args(argv)

    if a.demo:
        paths = demo.build(Path(a.demo))
        a.candidates = str(paths["candidates"])
        a.models = str(paths["models"])
        a.coverage = str(paths["coverage"])
        a.out = a.out or str(Path(a.demo) / "board" / ("blind.html" if a.blind else "index.html"))
        print(f"demo files under {a.demo}")
    if not a.candidates:
        ap.error("a candidates file or --demo")
    case = load.load_case(
        Path(a.candidates),
        Path(a.models) if Path(a.models).is_dir() else None,
        [Path(p) for p in a.persist] if a.persist is not None else None,
        Path(a.coverage) if a.coverage else None,
        Path(a.score) if a.score else None,
        Path(a.ledger) if a.ledger else None,
        a.top,
    )
    out = Path(a.out) if a.out else Path(a.candidates).parent / "board" / ("blind.html" if a.blind else "index.html")
    page, trace = render.write(case, out, a.blind)
    n_vals = len(json.loads(trace.read_text())["values"])
    for st in case.strips:
        finals = {g: r.value for g, r in st.shown_grade_counts.items()}
        print(f"{st.strip}: {len(st.candidates)} shown; final grades {finals}; model files {sorted(st.model_files)}")
    for n in case.notes:
        print(f"note: {n}")
    print(f"written: {page} ({n_vals} traced values; trace {trace})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
