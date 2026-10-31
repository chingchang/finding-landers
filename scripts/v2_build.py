"""What the v2 tag would freeze, and the proof that v2 is item 13's list and item 15a's column, plan item 16a.

    uv run scripts/v2_build.py model        the re-ranker's weights, from item 13's table: all ten tuning sites into
                                            landers/rerank_v2.npz, and one per left-out site under out/v2/folds
    uv run scripts/v2_build.py reference STRIP    the reference crop item 14's votes show, into landers/v2_reference.npz
    uv run --group rerank scripts/v2_build.py prove STRIP [STRIP ...] [--from-item-13-list]
                                            run v2 with the strip's fold and compare, off, fake, dry-run
    uv run --group rerank scripts/v2_build.py unseen STRIP      run v2 with the all-sites weights on a tuning strip item 13 never embedded

This is the only v2 code that reads the key, and only in ``model`` and when comparing after a run. Strips of a site that is
not a tuning site are refused. No paid model is called: the backends here are fake and dry-run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rerank as rr  # noqa: E402
from models_sam import strip_reader  # noqa: E402
from models_wonder import reference_spot  # noqa: E402

from landers import config, v2  # noqa: E402
from landers.rerank import model as rm  # noqa: E402
from landers.search.run import git_state  # noqa: E402
from landers.shape import ShapeRules, apply_rules_json  # noqa: E402
from landers.strip import Strip  # noqa: E402

OUT = config.REPO_ROOT / "out" / "v2"
FOLDS = OUT / "folds"
PROVE = OUT / "prove"
REPORT = config.REPO_ROOT / "docs" / "reports" / "2026-10-31-v2-assembled"
ITEM_14 = config.REPO_ROOT / "out" / "deep14" / "inputs" / "candidates_combined.json"
ITEM_15A = config.REPO_ROOT / "out" / "halfcal" / "column" / "candidates_combined.json"
DRY_14 = config.REPO_ROOT / "out" / "deep14_dry" / "model_requests"
NO_SITE = "(no site left out)"  # training_mask keeps every row, and "" is the site of rows that leave with none


def fitted(tb, site: str) -> rm.Fitted:
    pos = rm.is_positive(tb.source)
    mask = rm.training_mask(tb.source, tb.site, tb.target, site, None, True)
    return rm.fit(tb.emb[mask], tb.score[mask], tb.nov[mask], pos[mask].astype(float), rm.source_weights(tb.source[mask]), "primary")


def build_models(a) -> int:
    sites, thresholds, answers = rr.controls()
    t = rr.build_table(sites, thresholds, answers)
    tb = t["table"]
    encoder = rr.load(rr.OUT / "encoder.json")
    meta = {"variant": "primary", "encoder": encoder["model"], "revision": encoder["revision"], "protocol": "docs/proposals/reranker-v1-protocol.md"}  # no commit, so a rerun gives the same bytes
    for site in rr.site_strips(sites):
        v2.save_model(FOLDS / f"{site}.npz", fitted(tb, site), {**meta, "left_out": site})
        print(site, flush=True)
    keep = rm.training_mask(tb.source, tb.site, tb.target, NO_SITE, None, True)
    names, counts = np.unique(tb.source[keep], return_counts=True)
    rows = {str(k): int(v) for k, v in zip(names, counts, strict=True)}
    path = config.REPO_ROOT / v2.load_config()["rerank"]["model"]
    v2.save_model(path, fitted(tb, NO_SITE), {**meta, "left_out": None, "rows": rows})
    rr.write_json(OUT / "model.json", {"sha256": v2.sha256_of(path), "rows": rows, "git": git_state()})
    print(f"{path}: {rows}, sha256 {v2.sha256_of(path)}")
    return 0


def build_reference(a) -> int:
    strip = Strip.open(a.strip)
    at = reference_spot(strip, 0)
    size = 384  # the widest item 14 read: the probe's; a vote's 320 is its centre
    data, _ = strip_reader(strip)(at[0], at[1], size)
    path = config.REPO_ROOT / v2.load_config()["model_stage"]["reference"]
    v2.save_reference(path, data)
    narrow = strip_reader(strip)(at[0], at[1], 320)
    same = bool(np.array_equal(v2.Reference(path).read(size=320)[0], narrow[0]) and np.array_equal(v2.Reference(path).read(size=320)[1], narrow[1]))
    print(f"{path}: {data.shape}, the vote's 320 px equal to the strip's: {same}, sha256 {v2.sha256_of(path)}")
    return 0 if same else 1


def site_of(sites: dict, sid: str) -> str:
    for s in sites["sites"]:
        if sid in s["strips"]:
            if s["group"] != "tuning":
                raise SystemExit(f"{sid}: not a tuning strip; refused")
            return s["name"]
    raise SystemExit(f"{sid}: not on the control list; refused")


FIELDS = ("row", "col", "score", "branch", "grade", "area_px", "rank", "export_rank", "frozen_rank", "rerank_rank")


def differences(mine: list[dict], want: list[dict], fields: tuple) -> dict:
    """Position by position: nothing may differ, in value or in order."""
    n = sum(any(a.get(f) != b.get(f) for f in fields) for a, b in zip(mine, want, strict=False))
    return {"rows": len(mine), "rows_expected": len(want), "rows_differing": n}


def request_names(path: Path) -> set[str]:
    return {p.name for p in path.iterdir()} if path.exists() else set()


def source_list(sid: str, entry: dict) -> dict:
    """The detection against the top of the list item 13 took, by position and branch, so one extra row does not read as
    every row below it moving."""
    was = rr.load(rr.EXPORT / "strips" / sid / "index.json")
    rows, _ = v2.top_rows(entry["candidates"], 2000)
    keys = ("row", "col", "score", "branch", "grade", "area_px", "rank")

    def at(x):
        return x["row"], x["col"], x["branch"]

    a, b = {at(r): r for r in rows}, {at(r): r for r in was["rows"]}
    only_here, only_there = sorted(a.keys() - b.keys()), sorted(b.keys() - a.keys())
    both = a.keys() & b.keys()
    return {
        "item_13_took_it_from": was["source"], "candidates": len(entry["candidates"]), "candidates_in_item_13": was["candidates_total"],
        "rows_at_the_same_rank_differing": differences(rows, was["rows"], keys)["rows_differing"],
        "top_2000_only_here": [{**{k: a[x][k] for k in keys}} for x in only_here], "top_2000_only_in_item_13": [{**{k: b[x][k] for k in keys}} for x in only_there],
        "top_2000_in_both": len(both), "in_both_with_another_value": sum(any(a[x][k] != b[x][k] for k in ("score", "grade", "area_px")) for x in both),
    }  # fmt: skip


def item_13_list(sid: str) -> Path:
    """The strip's entry as item 13 took it: a v0.3 list with shape_v3 applied after de-duplication."""
    path = PROVE / f"item_13_list_{sid}.json"
    if not path.exists():
        d = rr.load(config.REPO_ROOT / "out" / "shape_v3" / "candidates_v03_features.json")["strips"][sid]
        rules = ShapeRules.load(config.REPO_ROOT / "landers" / "shape_v3.json")
        rr.write_json(path, {"strips": {sid: {**d, "candidates": [apply_rules_json(c, rules) for c in d["candidates"]]}}})
    return path


def prove(a) -> int:
    sites, thresholds, answers = rr.controls()
    want_14 = rr.load(ITEM_14)["strips"]
    want_15 = rr.load(ITEM_15A)["strips"]
    key_14 = rr.load(ITEM_14)["key_ranks"]
    path = REPORT / "proof.json"
    results = rr.load(path)["strips"] if path.exists() else {}
    tag = "item_13_list_" if a.from_item_13_list else ""
    for sid in a.ids:
        site = site_of(sites, sid)
        common = {
            "model_path": FOLDS / f"{site}.npz", "work": PROVE / f"strips_{tag}", "jobs": a.jobs, "log": print,
            "detections": {sid: str(item_13_list(sid))} if a.from_item_13_list else None,
        }  # fmt: skip
        off = v2.run_strips([sid], PROVE / f"off_{tag}{sid}", stage_on=False, **common)
        fake = v2.run_strips([sid], PROVE / f"fake_{tag}{sid}", stage_on=True, backend="fake", **common)
        v2.run_strips([sid], PROVE / f"dry_{tag}{sid}", stage_on=True, backend="dry-run", **common)

        mine, fake_rows = off["strips"][sid]["candidates"], fake["strips"][sid]["candidates"]
        requests = request_names(PROVE / f"dry_{tag}{sid}" / "model_requests")
        ranks = rr.key_ranks({sid: mine}, answers, thresholds)
        entry = v2.load_json(item_13_list(sid))["strips"][sid] if a.from_item_13_list else v2.load_json(common["work"] / sid / "detect.json")
        name = f"{sid}, from item 13's list" if a.from_item_13_list else f"{sid}, from the full strip"
        results[name] = {
            "site": site, "not_blind": True, "detection": "item 13's list" if a.from_item_13_list else "fresh, frozen-v1 detector on the full strip",
            "detection_against_item_13": source_list(sid, entry),
            "against_item_13_combined": differences(mine, want_14[sid]["candidates"], FIELDS),
            "against_item_15a_column": differences(mine, want_15[sid]["candidates"], (*FIELDS, "half_rate_per_km2", "half_rate_below_per_km2")),
            "key_ranks": ranks, "key_ranks_differing_from_item_14": {k: {"v2": v, "item_14": key_14.get(k)} for k, v in ranks.items() if key_14.get(k) != v},
            "fake_stage": {
                "same_list_as_off": fake_rows == mine, "calls": fake["model_stage"]["calls"],
                "votes": len(v2.load_json(PROVE / f"fake_{tag}{sid}" / f"votes_{sid}.json")["records"]),
                "review_stopped": v2.load_json(PROVE / f"fake_{tag}{sid}" / f"review_{sid}.json")["stopped"],
            },
            "dry_run_requests": {"files": len(requests), "also_in_item_14_dry_run": len(requests & request_names(DRY_14))},
            "files_read_stage_off": v2.load_json(PROVE / f"off_{tag}{sid}" / "files_read.json")["files"],
            "files_read_stage_fake": v2.load_json(PROVE / f"fake_{tag}{sid}" / "files_read.json")["files"],
        }  # fmt: skip
        print(name, {k: v for k, v in results[name].items() if k in ("against_item_13_combined", "against_item_15a_column", "key_ranks_differing_from_item_14", "fake_stage", "dry_run_requests")}, flush=True)
        write_proof("proof.json", {"what": "item 16a: v2 against item 13's combined list and item 15a's column, position by position", "git": git_state(), "strips": results})
    return 0


def write_proof(name: str, obj) -> None:
    rr.write_json(REPORT / name, obj)


def unseen(a) -> int:
    sites, _, _ = rr.controls()
    site_of(sites, a.id)
    if a.id in rr.load(ITEM_14)["strips"]:
        raise SystemExit(f"{a.id}: item 13 embedded this strip; name one it did not")
    out = OUT / f"unseen_{a.id}"
    r = v2.run_strips([a.id], out, stage_on=False, jobs=1, log=print)
    e = r["strips"][a.id]
    rows = e["candidates"]
    write_proof("unseen.json", {
        "what": "item 16a: the frozen files on a tuning strip item 13 never embedded, one process so the read guard covers the detector; no score, and the strip's site is in the model's training set",
        "strip": a.id, "git": r["git"], "candidates_total": e["candidates_total"], "listed": len(rows), "rows_with_a_measured_rate": sum(x["half_rate_per_km2"] is not None for x in rows),
        "rows_with_only_a_bound": sum(x["half_rate_below_per_km2"] is not None for x in rows), "ranks_are_a_permutation": sorted(x["rerank_rank"] for x in rows) == list(range(1, len(rows) + 1)),
        "files_read": v2.load_json(out / "files_read.json")["files"],
    })  # fmt: skip
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("model")
    r = sub.add_parser("reference")
    r.add_argument("strip", help="item 14's --reference")
    p = sub.add_parser("prove")
    p.add_argument("ids", nargs="+")
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--from-item-13-list", action="store_true", help="take detection from the list item 13 took instead of the full strip")
    u = sub.add_parser("unseen")
    u.add_argument("id")
    a = ap.parse_args(argv)
    return {"model": build_models, "reference": build_reference, "prove": prove, "unseen": unseen}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
