"""Search bookkeeping and, later, the search itself.

    uv run scripts/search.py survey [--run-log <detect log>] [--cell-m 100] [--out out/search]
    uv run scripts/search.py run --frozen [--same-code-as TAG] [--jobs 3] [--ids ID ...] [--limit N]

``survey`` reads every search strip's label and overview (no detector) and writes under --out:
inventory.json (one record per strip), overlaps.json (every pair that shares ground), coverage.json and
coverage.png (dates per grid cell), plan.json (order, tiles, time estimate from the run log's tiles per
second). ``run`` is for item 11: it refuses unless --frozen is given and HEAD carries an exact tag (or
--untagged, for a rehearsal), takes the strips in plan order, skips the ones already written, and writes
<out>/candidates/candidates_<id>.json per strip as each lands. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.detect import DetectorConfig  # noqa: E402
from landers.search import coverage as cov  # noqa: E402
from landers.search import inventory, plan, run  # noqa: E402

DEFAULT_OUT = config.REPO_ROOT / "out" / "search"
DEFAULT_CAL = config.REPO_ROOT / "landers" / "calibration_v0.json"
_RULE_FILES = sorted((config.REPO_ROOT / "landers").glob("shape_v*.json"))
DEFAULT_RULES = _RULE_FILES[-1] if _RULE_FILES else config.REPO_ROOT / "landers" / "shape_v1.json"


def survey(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = a.ids or inventory.manifest_ids(a.case)
    if not ids:
        print(f"no strips of case {a.case} in {config.manifest_path()}", file=sys.stderr)
        return 2
    cfg = DetectorConfig()
    t0 = time.time()

    def prog(rec):
        print(f"{rec.observation_id} {rec.date} {rec.valid_area_km2:.1f} km2 {rec.tiles} tiles {time.time() - t0:.0f}s")

    grid, records, cells, missing = inventory.survey(ids, a.cell_m, cfg.tile, cfg.overlap, progress=prog)
    inv = {
        "case": a.case,
        "manifest": str(config.manifest_path()),
        "on_disk": len(records),
        "missing": missing,
        "grid": grid.to_json(),
        "strips": [r.to_json() for r in records],
    }
    (out / "inventory.json").write_text(json.dumps(inv, indent=1))
    pairs = cov.overlaps(cells, grid)
    (out / "overlaps.json").write_text(json.dumps({"grid": grid.to_json(), "pairs": pairs}, indent=1))
    c = cov.coverage(cells, grid)
    (out / "coverage.json").write_text(json.dumps(cov.coverage_json(c), indent=1))
    cov.render(c, out / "coverage.png")
    if a.run_log:
        rate = plan.baseline_rate(a.run_log)
        p = plan.tiling_plan(records, rate)
        (out / "plan.json").write_text(json.dumps(p, indent=1))
        print(f"plan: {p['totals']}")
    else:
        print("no --run-log given: plan.json not written")
    print(f"coverage: union {c['union_km2']} km2, by dates {c['km2_by_dates']}; {len(pairs)} overlapping pairs")
    print(f"written under {out} in {time.time() - t0:.0f}s")
    return 0


def run_search(a) -> int:
    if not a.frozen:
        print("the search runs only with the detector frozen: pass --frozen (a person's decision)", file=sys.stderr)
        return 3
    state = run.git_state()
    if state["dirty"]:
        print("working tree is dirty; commit first", file=sys.stderr)
        return 3
    same = None
    if a.same_code_as:
        match = run.code_matches_tag(a.same_code_as)
        if not match:
            what = "is not a known tag" if match is None else "differs from HEAD in the detector's files"
            print(f"{a.same_code_as} {what} ({' '.join(run.FROZEN_PATHS)})", file=sys.stderr)
            return 3
        same = a.same_code_as
    if not state["tag"] and not same and not a.untagged:
        print(
            "HEAD has no exact tag; the search runs from a frozen tag, or with --same-code-as <tag> when the "
            "detector's files are identical to it (--untagged rehearses)",
            file=sys.stderr,
        )
        return 3
    out = Path(a.out) / "candidates"
    if a.ids:
        ids = list(a.ids)
    else:
        p = Path(a.plan)
        if not p.exists():
            print(f"{p} not found: run survey first or give --ids", file=sys.stderr)
            return 2
        ids = [s["observation_id"] for s in json.loads(p.read_text())["strips"]]
    todo = run.pending(ids, out)
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(ids)} strips, {len(ids) - len(run.pending(ids, out))} done, {len(todo)} to run now")
    cal = None if a.no_calibration else a.calibration
    rules = None if a.no_shape_rules else a.shape_rules
    rec_cfg, cfg = run.frozen_configs(cal, rules)
    for sid in todo:
        if config.find_strip(sid) is None:
            print(f"{sid}: not on disk, skipped")
            continue
        t = time.time()
        prog = lambda n, k, sid=sid: print(f"\r{sid} tiles={n} cands={k}", end="", flush=True)  # noqa: E731
        path, entry = run.run_strip(sid, cfg, out, jobs=a.jobs, progress=prog, record_cfg=rec_cfg, same_code_as=same)
        print(
            f"\r{sid}: {len(entry['candidates'])} candidates from {entry['tiles']} tiles "
            f"in {time.time() - t:.0f}s -> {path}",
            flush=True,
        )
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("survey", help="inventory, overlaps, coverage, plan; no detector")
    s.add_argument("--case", default=inventory.SEARCH_CASE)
    s.add_argument("--ids", nargs="*", default=None, help="only these strips (default: every strip of the case)")
    s.add_argument("--cell-m", type=float, default=100.0, help="coverage grid cell in metres")
    s.add_argument("--run-log", default=None, help="a detect.py log to take tiles per second from")
    s.add_argument("--out", default=str(DEFAULT_OUT))
    r = sub.add_parser("run", help="the search pass, frozen detector, one file per strip")
    r.add_argument("--frozen", action="store_true")
    r.add_argument("--untagged", action="store_true", help="allow a rehearsal from an untagged commit")
    r.add_argument("--ids", nargs="*", default=None)
    r.add_argument("--plan", default=str(DEFAULT_OUT / "plan.json"))
    r.add_argument("--limit", type=int, default=0, help="run at most this many strips now")
    r.add_argument("--jobs", type=int, default=1)
    r.add_argument("--calibration", default=str(DEFAULT_CAL) if DEFAULT_CAL.exists() else None)
    r.add_argument("--no-calibration", action="store_true")
    r.add_argument(
        "--shape-rules",
        default=str(DEFAULT_RULES) if DEFAULT_RULES.exists() else None,
        help="as scripts/detect.py: the newest landers/shape_v*.json by default",
    )
    r.add_argument("--no-shape-rules", action="store_true")
    r.add_argument(
        "--same-code-as",
        default=None,
        metavar="TAG",
        help="run from an untagged commit whose detector files are identical to TAG (recorded in each file)",
    )
    r.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    return survey(a) if a.cmd == "survey" else run_search(a)


if __name__ == "__main__":
    sys.exit(main())
