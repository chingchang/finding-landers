"""Search bookkeeping and, later, the search itself.

    uv run scripts/search.py survey [--run-log <detect log>] [--cell-m 100] [--out out/search]
    uv run scripts/search.py run --frozen [--same-code-as TAG] [--jobs 3] [--ids ID ...] [--limit N]
    uv run scripts/search.py nodes
    uv run scripts/search.py retry [--min-km2 10] [--limit N]
    uv run scripts/search.py survivors --persist-dirs persist persist_12c --name survivors_12c.json

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


def per_km2(a) -> float:
    return float(json.loads(Path(a.thresholds).read_text())["pass"]["max_false_alarms_per_km2"])


def load_entry(cands_dir: Path, sid: str, cache: dict) -> dict:
    if sid not in cache:
        if len(cache) >= 3:
            cache.pop(next(iter(cache)))
        cache[sid] = json.loads(run.strip_output(cands_dir, sid).read_text())["strips"][sid]
    return cache[sid]


def persist_pairs(a) -> int:
    from landers import persist as lp
    from landers.search import persistence as sp
    from landers.strip import Strip

    cands_dir = Path(a.out) / "candidates"
    out = Path(a.out) / "persist"
    out.mkdir(parents=True, exist_ok=True)
    rate = per_km2(a)
    pairs = [p for p in json.loads((Path(a.out) / "overlaps.json").read_text())["pairs"] if p["km2"] >= a.min_km2]
    pairs.sort(key=lambda p: -p["km2"])
    done = {sid for sid in (p[k] for p in pairs for k in ("a", "b")) if run.strip_output(cands_dir, sid).exists()}
    todo = [p for p in pairs if p["a"] in done and p["b"] in done and not (out / f"persist_{p['a']}_{p['b']}.json").exists()]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(pairs)} pairs sharing at least {a.min_km2} km2; {len(todo)} to run now", flush=True)
    cache: dict = {}
    for p in todo:
        t0 = time.time()
        ids = (p["a"], p["b"])
        strips = {sid: Strip.open(sid) for sid in ids}
        result = {"pair": list(ids), "km2_shared": p["km2"], "per_km2": rate, "radius_px": a.radius_px,
                  "git": run.git_state(), "directions": {}}
        for src, dst in (ids, ids[::-1]):
            ea, eb = load_entry(cands_dir, src, cache), load_entry(cands_dir, dst, cache)
            nodes = lp.offset_field(strips[src], strips[dst])
            surv = sp.survivors(ea, rate)
            recs, counts = sp.look_up(surv, eb["candidates"], strips[src], strips[dst], nodes, a.radius_px)
            result["directions"][f"{src}->{dst}"] = {
                "from": src,
                "to": dst,
                "registration": lp.nodes_summary(nodes),
                "nodes": lp.nodes_to_json(nodes),
                "survivors_of_from": len(surv),
                "counts": counts,
                "survivors": recs,
            }
            print(f"  {src} -> {dst}: {lp.nodes_summary(nodes)} {counts}", flush=True)
        result["seconds"] = round(time.time() - t0)
        path = out / f"persist_{p['a']}_{p['b']}.json"
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(result, indent=1))
        tmp.replace(path)
        print(f"{p['a']} {p['b']} ({p['km2']} km2) in {result['seconds']}s -> {path}", flush=True)
    return 0


def cache_nodes(a) -> int:
    """The registration nodes item 11 measured, per pair, in a form that needs no strip to read back."""
    from landers.search import register as rg

    count = 0
    for f in sorted((Path(a.out) / "persist").glob("persist_*.json")):
        d = json.loads(f.read_text())
        dirs = {k: {x: v[x] for x in ("from", "to", "registration", "nodes")} for k, v in d["directions"].items()}
        rg.write_nodes(Path(a.out) / "registration", d["pair"], d["km2_shared"], f"item 11, {f.name}", dirs)
        count += 1
    print(f"{count} pairs cached under {Path(a.out) / 'registration'}")
    return 0


def retry_pairs(a) -> int:
    """The pairs item 11 could not register, sharing at least --min-km2, again with the coarse offset measured
    at matched scales and the coarser strip resampled. Item 11's files are not touched: the results go to
    persist_12c/ and the nodes replace that pair's cache only if the retry registered it."""
    from landers import persist as lp
    from landers.search import persistence as sp
    from landers.search import register as rg
    from landers.strip import Strip

    cands_dir = Path(a.out) / "candidates"
    out = Path(a.out) / "persist_12c"
    out.mkdir(parents=True, exist_ok=True)
    rate = per_km2(a)
    failed = []
    for f in sorted((Path(a.out) / "persist").glob("persist_*.json")):
        d = json.loads(f.read_text())
        oks = [v["registration"]["ok"] for v in d["directions"].values()]
        if d["km2_shared"] >= a.min_km2 and not rg.is_registered(oks):
            failed.append((d["pair"], d["km2_shared"]))
    failed.sort(key=lambda p: -p[1])
    todo = [p for p in failed if not (out / f"persist_{p[0][0]}_{p[0][1]}.json").exists()]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(failed)} unregistered pairs sharing at least {a.min_km2} km2; {len(todo)} to run now", flush=True)
    cache: dict = {}
    for ids, km2 in todo:
        t0 = time.time()
        strips = {sid: Strip.open(sid) for sid in ids}
        result = {"pair": list(ids), "km2_shared": km2, "per_km2": rate, "radius_px": a.radius_px, "radius_m": a.radius_px * 0.25,
                  "method": "12c retry", "git": run.git_state(), "directions": {}}
        for src, dst in (ids, ids[::-1]):
            ea, eb = load_entry(cands_dir, src, cache), load_entry(cands_dir, dst, cache)
            nodes, how = rg.offset_field(strips[src], strips[dst])
            surv = sp.survivors(ea, rate)
            # the same 2 m and the same node reach on the ground as item 11, whatever the two scales
            radius = a.radius_px * 0.25 / strips[dst].label.scale_m
            reach = 8192.0 * 0.25 / strips[src].label.scale_m
            recs, counts = sp.look_up(surv, eb["candidates"], strips[src], strips[dst], nodes, radius, reach)
            result["directions"][f"{src}->{dst}"] = {
                "from": src,
                "to": dst,
                "radius_px": radius,
                "how": how,
                "registration": lp.nodes_summary(nodes),
                "nodes": lp.nodes_to_json(nodes),
                "survivors_of_from": len(surv),
                "counts": counts,
                "survivors": recs,
            }
            print(f"  {src} -> {dst}: {lp.nodes_summary(nodes)} {counts}", flush=True)
        result["seconds"] = round(time.time() - t0)
        path = out / f"persist_{ids[0]}_{ids[1]}.json"
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(result, indent=1))
        tmp.replace(path)
        oks = [v["registration"]["ok"] for v in result["directions"].values()]
        if rg.is_registered(oks):
            dirs = {k: {x: v[x] for x in ("from", "to", "registration", "nodes")} for k, v in result["directions"].items()}
            rg.write_nodes(Path(a.out) / "registration", list(ids), km2, f"12c retry, {path.name}", dirs)
        print(f"{ids[0]} {ids[1]} ({km2} km2) in {result['seconds']}s -> {path}", flush=True)
    return 0


def load_pair_results(root: Path, dirs: list[str]) -> list[dict]:
    """One result per pair; a pair in a later directory replaces the same pair in an earlier one."""
    results: dict = {}
    for name in dirs:
        for f in sorted((root / name).glob("persist_*.json")):
            d = json.loads(f.read_text())
            results[tuple(d["pair"])] = d
    return [results[k] for k in sorted(results)]


def combine_survivors(a) -> int:
    from landers.search import persistence as sp

    cands_dir = Path(a.out) / "candidates"
    rate = per_km2(a)
    plan_ids = [s["observation_id"] for s in json.loads(Path(a.plan).read_text())["strips"]]
    ids = [sid for sid in plan_ids if run.strip_output(cands_dir, sid).exists()]
    surv, per_strip = {}, {}
    for sid in ids:
        d = json.loads(run.strip_output(cands_dir, sid).read_text())
        e = d["strips"][sid]
        surv[sid] = sp.survivors(e, rate)
        per_strip[sid] = {
            "tiles": e["tiles"],
            "valid_area_km2": e["valid_area_km2"],
            "candidates": len(e["candidates"]),
            "candidates_per_km2": round(len(e["candidates"]) / e["valid_area_km2"], 2),
            "survivors": len(surv[sid]),
            "survivor_min_score": surv[sid][-1]["score"] if surv[sid] else None,
            "seconds": d["seconds"],
            "commit": d["git"]["commit"],
            "same_code_as": d["git"].get("same_code_as"),
            "family_counts": sp.family_counts(e["candidates"]),
            "scale_m": e["scale_m"],
        }
        del d, e
    results = load_pair_results(Path(a.out), a.persist_dirs)
    rows = sp.combine(ids, surv, results)
    chance = [sp.chance_matches(pr, surv, per_strip) for pr in results]
    chance = [c for pair in chance for c in pair]
    by_looked: dict = {}
    by_branch: dict = {}
    for r in rows:
        k = f"{r['dates_seen']} of {r['dates_looked']}"
        by_looked[k] = by_looked.get(k, 0) + 1
        b = by_branch.setdefault(r["branch"], {"survivors": 0, "looked_on_another_date": 0, "seen_on_two_or_more": 0,
                                               "looked_never_seen_again": 0})
        b["survivors"] += 1
        b["looked_on_another_date"] += r["dates_looked"] > 1
        b["seen_on_two_or_more"] += r["dates_seen"] > 1
        b["looked_never_seen_again"] += r["dates_looked"] > 1 and r["dates_seen"] == 1
    registration = [
        {"from": d["from"], "to": d["to"], **d["registration"], "counts": d["counts"]}
        for pr in results
        for d in pr["directions"].values()
    ]
    # a pair counts as registered when either direction has at least 4 ok nodes (the outlier test needs 4)
    pairs = []
    for pr in results:
        oks = [d["registration"]["ok"] for d in pr["directions"].values()]
        pairs.append({"pair": pr["pair"], "km2_shared": pr["km2_shared"], "ok_nodes": oks, "registered": max(oks) >= 4})
    reg_km2 = round(sum(p["km2_shared"] for p in pairs if p["registered"]), 2)
    all_km2 = round(sum(p["km2_shared"] for p in pairs), 2)
    out = {
        "what": "survivors of the frozen-v1 search: top candidates per strip at the adopted false-alarm bar, "
        "with persistence across every other date that covers them. Grades are the detector's; nothing here "
        "raises one.",
        "per_km2": rate,
        "persist_dirs": a.persist_dirs,
        "strips_searched": len(ids),
        "strips_in_plan": len(plan_ids),
        "pairs_with_persistence": len(results),
        "survivors": len(rows),
        "dates_seen_of_looked": dict(sorted(by_looked.items())),
        "by_branch": by_branch,
        "registration": registration,
        "pairs": {
            "what": "every overlapping pair; registered when either direction has at least 4 ok nodes. Shared km2 "
            "is summed over pairs, so ground under three dates counts in three pairs.",
            "n": len(pairs),
            "registered": sum(p["registered"] for p in pairs),
            "km2_shared_all": all_km2,
            "km2_shared_registered": reg_km2,
            "list": pairs,
        },
        "chance": {
            "what": "per pair direction: survivors looked up on the other date, how many were seen, and how many "
            "would be seen by chance if the other date's candidates of the same family were spread evenly over "
            "its valid ground (sum over survivors of 1 - exp(-density * pi * radius^2))",
            "looked": sum(c["looked"] for c in chance),
            "seen": sum(c["seen"] for c in chance),
            "expected_by_chance": round(sum(c["expected_by_chance"] for c in chance), 1),
            "directions": chance,
        },
        "per_strip": per_strip,
        "rows": rows,
    }
    (Path(a.out) / a.name).write_text(json.dumps(out, indent=1))
    print(f"{len(rows)} survivors over {len(ids)} strips; seen of looked: {out['dates_seen_of_looked']}")
    return 0


def searched_coverage(a) -> int:
    cands_dir = Path(a.out) / "candidates"
    inv = json.loads((Path(a.out) / "inventory.json").read_text())
    ids = [s["observation_id"] for s in inv["strips"] if run.strip_output(cands_dir, s["observation_id"]).exists()]
    grid, records, cells, _ = inventory.survey(ids, inv["grid"]["cell_m"], DetectorConfig().tile, DetectorConfig().overlap)
    c = cov.coverage(cells, grid)
    j = cov.coverage_json(c)
    j["what"] = "ground searched by the frozen-v1 detector: number of searched dates per cell"
    j["strips"] = ids
    (Path(a.out) / "searched_coverage.json").write_text(json.dumps(j, indent=1))
    cov.render(c, Path(a.out) / "searched_coverage.png", title="Ground searched by the frozen detector, by number of dates")
    print(f"searched: {len(ids)} strips, union {c['union_km2']} km2, by dates {c['km2_by_dates']}")
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
    thresholds = str(config.REPO_ROOT / "controls" / "thresholds.json")
    q = sub.add_parser("persist", help="register every overlapping pair of searched strips; survivors looked up")
    q.add_argument("--min-km2", type=float, default=0.0, help="only pairs sharing at least this much ground")
    q.add_argument("--radius-px", type=float, default=8.0, help="as scripts/persist.py")
    q.add_argument("--limit", type=int, default=0)
    q.add_argument("--thresholds", default=thresholds)
    q.add_argument("--out", default=str(DEFAULT_OUT))
    v = sub.add_parser("survivors", help="combine the per-strip survivors and the pair files into survivors.json")
    v.add_argument("--thresholds", default=thresholds)
    v.add_argument("--plan", default=str(DEFAULT_OUT / "plan.json"))
    v.add_argument("--out", default=str(DEFAULT_OUT))
    v.add_argument("--persist-dirs", nargs="+", default=["persist"], help="later directories replace a pair in earlier ones")
    v.add_argument("--name", default="survivors.json")
    n = sub.add_parser("nodes", help="cache item 11's registration nodes under <out>/registration")
    n.add_argument("--out", default=str(DEFAULT_OUT))
    t = sub.add_parser("retry", help="the unregistered pairs again, across scales; results under <out>/persist_12c")
    t.add_argument("--min-km2", type=float, default=10.0)
    t.add_argument("--radius-px", type=float, default=8.0, help="at 0.25 m per pixel; scaled to the other strip's pixels")
    t.add_argument("--limit", type=int, default=0)
    t.add_argument("--thresholds", default=thresholds)
    t.add_argument("--out", default=str(DEFAULT_OUT))
    g = sub.add_parser("coverage", help="coverage of the strips searched so far (searched_coverage.json, .png)")
    g.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    cmds = {"survey": survey, "run": run_search, "persist": persist_pairs, "survivors": combine_survivors,
            "coverage": searched_coverage, "nodes": cache_nodes, "retry": retry_pairs}
    return cmds[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
