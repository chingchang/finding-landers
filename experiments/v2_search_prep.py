"""Plan item 16b: v2's list on the search strips, before the freeze, as preparation only. Nothing is published from it.

    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py run [--limit N]
    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py check
    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py repeat STRIP

scripts/v2.py refuses to start without the tag, which is a person's, and the plan asks for this pass before it. So this calls
the same function that command calls, on the same frozen files and the same search lists, with ``frozen=False``: the lists say
they are not frozen, and scripts/score.py --heldout refuses them. It does not stand in for item 17's run.

The strips and their order come from item 16a's search_commands.txt. A strip on the control list is refused before anything
opens. Timings and counts go to the report's directory; the rows stay under out/, and nothing here prints or ranks them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config, v2  # noqa: E402
from landers.search.run import git_state  # noqa: E402

COMMANDS = config.REPO_ROOT / "docs" / "reports" / "2026-10-31-v2-assembled" / "search_commands.txt"
LISTS = config.REPO_ROOT / "out" / "search" / "candidates"
OUT = config.REPO_ROOT / "out" / "v2" / "search_prep"
REPORT = config.REPO_ROOT / "docs" / "reports" / "2026-10-31-v2-search-prep"


def search_strips(text: str) -> list[str]:
    """One strip per command, in the plan's order; the closing command names them all again."""
    strips = []
    for line in text.splitlines():
        m = re.match(r"uv run .*scripts/v2\.py (\S+) --out ", line)
        if m:
            strips.append(m.group(1))
    if len(strips) != len(set(strips)):
        raise ValueError("a strip appears twice")
    return strips


def refuse_controls(strips: list[str], sites: dict) -> None:
    listed = {i for s in sites["sites"] for i in s["strips"]}
    named = sorted(set(strips) & listed)
    if named:
        raise SystemExit(f"{named}: on the control list; this pass is for search strips only")


def seconds_of(line: str) -> tuple[str, str, float] | None:
    """(strip, step, seconds) from one of v2.strip_list's log lines. Seconds count from that strip's start."""
    m = re.match(r"(\S+): (?:(\d+) crops embedded|list of \d+ of \d+), (\d+)s$", line)
    if not m:
        return None
    return m.group(1), "embedded" if m.group(2) else "listed", float(m.group(3))


def strips_to_run() -> list[str]:
    strips = search_strips(COMMANDS.read_text())
    refuse_controls(strips, v2.load_json(config.REPO_ROOT / "controls" / "sites.json"))
    return strips


def run(a) -> int:
    strips = strips_to_run()
    if a.limit:
        done = [s for s in strips if (OUT / "strips" / s / "list.json").exists()]
        strips = done + [s for s in strips if s not in done][: a.limit]
    path = REPORT / "timings.json"
    was = v2.load_json(path) if path.exists() else {"strips": {}}

    def log(line: str) -> None:
        print(line, flush=True)
        got = seconds_of(line)
        if got:
            was["strips"].setdefault(got[0], {})[got[1] + "_s"] = got[2]
            was["strips"][got[0]]["git"] = git_state()["commit"]
            v2.write_json(path, was)

    t0 = time.time()
    v2.run_strips(strips, OUT, stage_on=False, frozen=False, jobs=1, detections={s: str(LISTS / f"candidates_{s}.json") for s in strips}, log=log)
    print(f"{len(strips)} strips in this call, {time.time() - t0:.0f}s", flush=True)
    return 0


def check(a) -> int:
    """Shape only: each list is the top of its frozen-v1 list, re-ordered, with both ranks whole and the column present."""
    out = {}
    for s in strips_to_run():
        p = OUT / "strips" / s / "list.json"
        if not p.exists():
            out[s] = {"listed": None}
            continue
        d = v2.load_json(p)
        rows = d["candidates"]
        source = v2.load_json(LISTS / f"candidates_{s}.json")["strips"][s]["candidates"]
        top, _ = v2.top_rows(source, v2.load_config()["rerank"]["top"])
        whole = list(range(1, len(rows) + 1))
        out[s] = {
            "candidates_on_the_frozen_v1_list": len(source),
            "candidates_recorded": d["candidates_total"],
            "listed": len(rows),
            "same_rows_as_the_frozen_v1_top": {(x["row"], x["col"], x["branch"]) for x in rows} == {(x["row"], x["col"], x["branch"]) for x in top},
            "frozen_ranks_whole": sorted(x["frozen_rank"] for x in rows) == whole,
            "rerank_ranks_whole": sorted(x["rerank_rank"] for x in rows) == whole,
            "rows_with_a_measured_rate": sum(x["half_rate_per_km2"] is not None for x in rows),
            "rows_with_only_a_bound": sum(x["half_rate_below_per_km2"] is not None for x in rows),
            "rows_with_neither": sum(x["half_rate_per_km2"] is None and x["half_rate_below_per_km2"] is None for x in rows),
        }
    state = v2.load_json(OUT / "run.json")
    v2.write_json(REPORT / "check.json", {
        "what": "item 16b: shape of each search strip's v2 list; no row, score or rank is recorded here", "git": git_state(),
        "model_sha256": state["model_sha256"], "stage_on": state["stage_on"], "frozen": state["detector"]["frozen"],
        "frozen_files_against_item_16a": frozen_files_against_16a(), "strips": out,
    })  # fmt: skip
    print(json.dumps({k: sum(bool(v.get(k)) for v in out.values()) for k in ("listed", "same_rows_as_the_frozen_v1_top", "frozen_ranks_whole", "rerank_ranks_whole")}))
    return 0


def frozen_files_against_16a() -> dict:
    """Every file item 16a's freeze list names, hashed again now."""
    want = v2.load_json(COMMANDS.parent / "freeze.json")["sha256"]
    differ = sorted(k for k, h in want.items() if not (config.REPO_ROOT / k).exists() or v2.sha256_of(config.REPO_ROOT / k) != h)
    return {"files": len(want), "differing": differ}


def repeat(a) -> int:
    """One strip again from nothing, into another directory: does the same command give the same list, byte for byte?"""
    if a.strip not in strips_to_run():
        raise SystemExit(f"{a.strip}: not a search strip")
    other = OUT.parent / "search_prep_repeat"
    t0 = time.time()
    v2.run_strips([a.strip], other, stage_on=False, frozen=False, jobs=1, detections={a.strip: str(LISTS / f"candidates_{a.strip}.json")}, log=print)
    mine, first = other / "strips" / a.strip / "list.json", OUT / "strips" / a.strip / "list.json"
    v2.write_json(REPORT / "repeat.json", {
        "what": "item 16b: one strip's list computed twice from its frozen-v1 list", "strip": a.strip, "git": git_state(),
        "byte_identical": mine.read_bytes() == first.read_bytes(), "seconds": round(time.time() - t0),
    })  # fmt: skip
    print("byte identical:", mine.read_bytes() == first.read_bytes())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, default=0, help="at most this many strips not yet written")
    sub.add_parser("check")
    p = sub.add_parser("repeat")
    p.add_argument("strip")
    a = ap.parse_args(argv)
    return {"run": run, "check": check, "repeat": repeat}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
