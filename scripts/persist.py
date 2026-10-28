"""Persistence between two dates of a control site.

    uv run scripts/persist.py out/baseline_v1/candidates_baseline_v1.json --site schiaparelli
    uv run scripts/persist.py <candidates.json> --pair <id A> <id B> [--inject-check 4]

Registers date B to date A on a sparse grid, maps every candidate of A into B and marks it seen when B's
own candidate list has one of the same family within the match radius; then the same from B to A. Writes
<candidates dir>/persist_<site>.json with the registration nodes, the counts by branch and the annotated
candidates (grade "candidate" when seen on both dates). --inject-check draws synthetic objects into N tiles
of A, which B cannot contain, and reports how many are wrongly seen in B.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config, persist  # noqa: E402
from landers.detect import DetectorConfig, detect_tile, load_calibration  # noqa: E402
from landers.inject import InjectConfig, inject  # noqa: E402
from landers.score import load_json, match_radius_px  # noqa: E402
from landers.strip import Strip  # noqa: E402


def by_branch(cands: list[dict]) -> dict:
    out: dict = {}
    for c in cands:
        s = out.setdefault(c["branch"], {"n": 0, "seen": 0})
        s["n"] += 1
        if c.get("extra", {}).get("persist", {}).get("seen"):
            s["seen"] += 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--site", default=None)
    ap.add_argument("--pair", nargs=2, default=None, metavar=("A", "B"))
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--thresholds", default=str(config.REPO_ROOT / "controls" / "thresholds.json"))
    ap.add_argument("--spacing", type=int, default=4096)
    ap.add_argument("--inject-check", type=int, default=0, help="tiles of A to inject into and map to B")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    run = load_json(a.candidates)
    if a.pair:
        ida, idb = a.pair
        name = f"{ida}_{idb}"
    elif a.site:
        site = {s["name"]: s for s in load_json(a.sites)["sites"]}[a.site]
        if site["group"] in ("heldout", "final_exam"):
            print(f"{a.site} is {site['group']}: refused", file=sys.stderr)
            return 3
        if len(site["strips"]) < 2:
            print(f"{a.site} has one strip; persistence needs two", file=sys.stderr)
            return 2
        ida, idb = site["strips"][:2]
        name = a.site
    else:
        ap.error("--site or --pair")
    for sid in (ida, idb):
        if sid not in run["strips"]:
            print(f"{sid}: not in this run", file=sys.stderr)
            return 2
    thresholds = load_json(a.thresholds) if Path(a.thresholds).exists() else {"match_radius_px": 20}
    strips = {sid: Strip.open(sid) for sid in (ida, idb)}
    result = {"run": run.get("run"), "git_commit": run.get("git_commit"), "pair": [ida, idb], "directions": {}}
    t0 = time.time()
    for src, dst in ((ida, idb), (idb, ida)):
        sa, sb = strips[src], strips[dst]
        print(f"registering {dst} to {src} ...", flush=True)
        nodes = persist.offset_field(
            sa, sb, spacing=a.spacing, progress=lambda n, k: print(f"\r  nodes {n} ok {k}", end="", flush=True)
        )
        print()
        summ = persist.nodes_summary(nodes)
        print(f"  {summ}")
        radius = match_radius_px(thresholds, sa.label.scale_m)
        cands = copy.deepcopy(run["strips"][src]["candidates"])
        counts = persist.annotate(cands, run["strips"][dst]["candidates"], sa, sb, nodes, radius)
        branches = by_branch(cands)
        print(f"  {src} -> {dst}: {counts}; by branch {branches}")
        direction = {
            "from": src,
            "to": dst,
            "registration": summ,
            "nodes": persist.nodes_to_json(nodes),
            "match_radius_px": radius,
            "counts": counts,
            "by_branch": branches,
            "candidates": cands,
        }
        if a.inject_check and src == ida:
            dcfg = DetectorConfig(calibration=run["detector"].get("calibration"))
            if dcfg.calibration and not Path(dcfg.calibration).is_absolute():
                dcfg.calibration = str(config.REPO_ROOT / dcfg.calibration)
            cal = load_calibration(dcfg)
            rng = np.random.default_rng(0)
            tiles = list(sa.tiles(dcfg.tile, dcfg.overlap))
            pick = [
                tiles[i] for i in np.linspace(0, len(tiles) - 1, min(a.inject_check, len(tiles))).round().astype(int)
            ]
            n_obj = n_seen = 0
            for r0, r1, c0, c1 in pick:
                win = sa.read(r0, r1, c0, c1)
                if win.valid.mean() < 0.5:
                    continue
                injected, objs = inject(win, sa.label, InjectConfig(), rng, 3)
                tc = detect_tile(injected, sa.label, dcfg)
                if cal is not None:
                    from landers.calibrate import apply

                    tc = apply(tc, cal)
                found = [
                    c.to_json()
                    for c in tc
                    if any(np.hypot(c.row - (r0 + o.row), c.col - (c0 + o.col)) <= radius for o in objs)
                ]
                persist.annotate(found, run["strips"][dst]["candidates"], sa, sb, nodes, radius)
                n_obj += len(found)
                n_seen += sum(1 for c in found if c["extra"]["persist"].get("seen"))
            direction["inject_check"] = {
                "tiles": len(pick),
                "injected_detected": n_obj,
                "wrongly_seen_in_other_date": n_seen,
            }
            print(f"  inject check: {n_obj} injected objects detected in {src}, {n_seen} wrongly seen in {dst}")
        result["directions"][f"{src}->{dst}"] = direction
    result["seconds"] = round(time.time() - t0)
    out = Path(a.out) if a.out else Path(a.candidates).parent / f"persist_{name}.json"
    out.write_text(json.dumps(result, indent=1))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
