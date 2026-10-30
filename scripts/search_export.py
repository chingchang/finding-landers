"""Crop export for item 12c, and the check a person reads before any JP2 is deleted.

    uv run scripts/search_export.py export [--ids ID ...] [--limit N]
    uv run scripts/search_export.py pieces
    uv run scripts/search_export.py tiles
    uv run scripts/search_export.py labels
    uv run scripts/search_export.py check

``export`` takes the search strips first, then the tuning strips, and skips any strip whose index.json exists.
``check`` reads everything back and writes out/export/check.json and check.md. This script deletes nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers import persist as lp  # noqa: E402
from landers import transplant as tp  # noqa: E402
from landers.search import export as ex  # noqa: E402
from landers.search import inventory, run  # noqa: E402
from landers.search import persistence as sp  # noqa: E402
from landers.search import register as rg  # noqa: E402
from landers.shape import ShapeRules, apply_rules_json  # noqa: E402
from landers.search.export import WindowStrip  # noqa: E402
from landers.strip import Strip  # noqa: E402

DEFAULT_OUT = config.REPO_ROOT / "out" / "export"
SEARCH_OUT = config.REPO_ROOT / "out" / "search"
TUNING_LISTS = [
    # the frozen-v1 lists of the tuning strips, as item 9c took them: same candidates, shape_v3 applied here
    (config.REPO_ROOT / "out" / "shape_v3" / "candidates_v03_features.json", config.REPO_ROOT / "landers" / "shape_v3.json"),
    (config.REPO_ROOT / "out" / "heldout_v1" / "candidates_heldout_v1.json", None),
    (config.REPO_ROOT / "out" / "heldout_v1" / "candidates_final_exam_v1.json", None),
]
TRANSPLANT_LIST = config.REPO_ROOT / "out" / "transplant_t1" / "transplant_t1.json"
SAMPLE = 20  # crops per strip compared pixel for pixel with the JP2


def load(path) -> dict:
    return json.loads(Path(path).read_text())


def controls() -> tuple[dict, dict]:
    return load(config.REPO_ROOT / "controls" / "sites.json"), load(config.REPO_ROOT / "controls" / "thresholds.json")


def roles() -> dict[str, str]:
    sites, _ = controls()
    return ex.exportable_strips(sites, config.manifest_path().read_text(), inventory.SEARCH_CASE)


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def export_one(sid: str, candidates: list[dict], source: dict, a) -> None:
    t0 = time.time()
    strip = Strip.open(sid)
    rows = ex.rank_top(candidates, a.top)
    meta = {"candidates_total": len(candidates), "source": source}
    index = ex.export_strip(strip, rows, a.size, Path(a.out) / "strips" / sid, meta)
    ex.copy_label(strip.jp2_path, Path(a.out) / "labels")
    mb = sum(f.stat().st_size for f in (Path(a.out) / "strips" / sid).iterdir()) / 1e6
    print(f"{sid}: {index['n_crops']} crops of {len(candidates)}, {index['block_reads']} block reads, {mb:.0f} MB, "
          f"{time.time() - t0:.0f}s, {free_gb(Path(a.out)):.1f} GB free", flush=True)


def export_crops(a) -> int:
    out = Path(a.out)
    (out / "strips").mkdir(parents=True, exist_ok=True)
    all_roles = roles()
    wanted = a.ids or [s for r in ("search", "tuning") for s, v in all_roles.items() if v == r]
    sites, _ = controls()
    for sid in wanted:
        ex.refuse_blind(sites, sid)
    done = lambda sid: (out / "strips" / sid / "index.json").exists()  # noqa: E731
    todo = [s for s in wanted if not done(s)]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(wanted)} strips, {len(wanted) - len([s for s in wanted if not done(s)])} done, {len(todo)} to run now", flush=True)

    def room() -> bool:
        if free_gb(out) < a.min_free_gb:
            print(f"stopping: under {a.min_free_gb} GB free", file=sys.stderr, flush=True)
            return False
        return True

    for sid in [s for s in todo if all_roles.get(s) == "search"]:
        if not room():
            return 4
        d = json.loads(run.strip_output(SEARCH_OUT / "candidates", sid).read_text())
        src = {"file": str(run.strip_output(SEARCH_OUT / "candidates", sid).relative_to(config.REPO_ROOT)),
               "detector": d["detector"].get("version"), "commit": d["git"]["commit"], "same_code_as": d["git"].get("same_code_as")}
        export_one(sid, d["strips"][sid]["candidates"], src, a)
        del d
    rest = {s for s in todo if all_roles.get(s) == "tuning"}
    for path, rules_path in TUNING_LISTS:
        if not rest:
            break
        d = load(path)
        rules = ShapeRules.load(rules_path) if rules_path else None
        for sid in sorted(rest & set(d["strips"])):
            if not room():
                return 4
            cands = d["strips"][sid]["candidates"]
            if rules:
                cands = [apply_rules_json(c, rules) for c in cands]
            src = {"file": str(path.relative_to(config.REPO_ROOT)), "detector": d["detector"].get("version"),
                   "commit": d.get("git_commit"), "rules_applied_here": rules_path.name if rules_path else None}
            export_one(sid, cands, src, a)
            rest.discard(sid)
        del d
    if rest:
        print(f"no candidate list for {sorted(rest)}", file=sys.stderr)
        return 2
    return 0


def piece_sites() -> tuple[list[dict], dict]:
    sites, thresholds = controls()
    answers = load(config.REPO_ROOT / "controls" / "tuning.json")
    return tp.key_pieces(answers, thresholds, tp.tuning_sources(sites)), tp.TransplantConfig()


def export_pieces(a) -> int:
    """A window around every recorded piece and every sham position: wide enough for ``cut_piece`` to run from it."""
    out = Path(a.out) / "pieces"
    out.mkdir(parents=True, exist_ok=True)
    pieces, cfg = piece_sites()
    by_strip: dict[str, list[dict]] = {}
    for p in pieces:
        by_strip.setdefault(p["strip"], []).append(p)
    records = []
    listed_shams = {}
    for c in load(TRANSPLANT_LIST)["cuts"]:
        if c["sham"]:
            listed_shams[(c["source"], c["site"], c["piece"])] = (c["row"], c["col"])
    half = a.piece_size // 2
    for sid, plist in sorted(by_strip.items()):
        strip = Strip.open(sid)
        all_pos = [(p["row"], p["col"]) for p in plist]
        for p in plist:
            radius = tp.cut_radius_px(p["size_m"], strip.label, cfg)
            sham = tp.sham_position(strip, p["row"], p["col"], radius, all_pos, cfg)
            for is_sham, pos in ((False, (p["row"], p["col"])), (True, sham)):
                base = {k: p[k] for k in ("site", "piece", "kind", "strip", "size_m")}
                if pos is None:
                    records.append({**base, "sham": is_sham, "file": None, "note": "no sham position found"})
                    continue
                r, c = int(round(pos[0])), int(round(pos[1]))
                name = f"{sid}__{p['site']}__{p['piece']}{'__sham' if is_sham else ''}.npz"
                win = strip.read(r - half, r + half, c - half, c + half)
                ex.write_window(out / name, win.data, win.row0, win.col0)
                rec = {**base, "sham": is_sham, "row": pos[0], "col": pos[1], "radius_px": radius, "file": name,
                       "sha256": ex.sha256(out / name)}
                if is_sham:
                    t1 = listed_shams.get((sid, p["site"], p["piece"]))
                    rec["same_as_transplant_t1"] = t1 is not None and abs(t1[0] - pos[0]) < 0.11 and abs(t1[1] - pos[1]) < 0.11
                records.append(rec)
        print(f"{sid}: {len(plist)} pieces", flush=True)
    (Path(a.out) / "pieces.json").write_text(json.dumps({"window_px": a.piece_size, "config": cfg.to_json(), "pieces": records}, indent=1))
    print(f"{len(records)} windows under {out}")
    return 0


def export_tiles(a) -> int:
    """The target tiles of the injection tuning ground, the fixed list in out/transplant_t1 and no others: the
    decision of 2026-10-29 02:00 names that list as the only part of the search area used for tuning."""
    out = Path(a.out) / "tiles"
    out.mkdir(parents=True, exist_ok=True)
    t = load(TRANSPLANT_LIST)
    records = []
    used = {p["tile"] for p in t["placements"]}  # the plan drew more tiles than got a placement; only these were used
    for sid, e in sorted(t["targets"].items()):
        strip = Strip.open(sid)
        ex.copy_label(strip.jp2_path, Path(a.out) / "labels")
        for r0, r1, c0, c1 in e["tiles"]:
            name = f"{sid}_{r0}_{c0}.npz"
            if f"{sid}:{r0}:{c0}" not in used:
                (out / name).unlink(missing_ok=True)
                continue
            if not (out / name).exists():
                win = strip.read(r0, r1, c0, c1)
                ex.write_window(out / name, win.data, win.row0, win.col0)
            records.append({"strip": sid, "row0": r0, "row1": r1, "col0": c0, "col1": c1, "file": name,
                            "sha256": ex.sha256(out / name)})
        print(f"{sid}: {len(e['tiles'])} tiles", flush=True)
    (Path(a.out) / "tiles.json").write_text(json.dumps({"source": str(TRANSPLANT_LIST.relative_to(config.REPO_ROOT)), "tiles": records}, indent=1))
    print(f"{len(records)} tiles under {out}")
    return 0


def export_labels(a) -> int:
    """Every label under the strips directory, except any of a site that is not a tuning site."""
    sites, _ = controls()
    blind = {sid for s in sites["sites"] if s["group"] != "tuning" for sid in s["strips"]}
    n = 0
    for lbl in sorted(config.strips_dir().rglob("*.LBL")):
        if lbl.name.split("_RED")[0] not in blind:
            ex.copy_label(lbl.with_suffix(".JP2"), Path(a.out) / "labels")
            n += 1
    print(f"{n} labels under {Path(a.out) / 'labels'}")
    return 0


def check_strip(root: Path, sid: str, role: str, top: int, rng: np.random.Generator) -> dict:
    out = {"strip": sid, "role": role, "problems": []}
    d = root / "strips" / sid
    if not (d / "index.json").exists():
        out["problems"].append("no index.json")
        return out
    es = ex.ExportedStrip(root, sid)
    idx = es.index
    out.update({"candidates_total": idx["candidates_total"], "expected": min(top, idx["candidates_total"]), "exported": idx["n_crops"],
                "crop_size_px": idx["crop_size_px"], "source": idx["source"]["file"]})
    if out["expected"] != out["exported"]:
        out["problems"].append("count differs")
    read_back = 0
    nodata_only = 0
    for ch in idx["chunks"]:
        p = d / ch["file"]
        if ex.sha256(p) != ch["sha256"]:
            out["problems"].append(f"{ch['file']}: sha256 differs")
        with np.load(p) as z:
            x = ex.join_bytes(z["low"], z["high"])
            ranks = z["ranks"]
        if x.shape != (ch["n"], idx["crop_size_px"], idx["crop_size_px"]) or int(ranks[0]) != ch["first_rank"]:
            out["problems"].append(f"{ch['file']}: shape or rank differs")
        if x.size and int(x.max()) > 1023:
            out["problems"].append(f"{ch['file']}: value above 1023")
        read_back += len(x)
        nodata_only += int(((x != 0).reshape(len(x), -1).sum(axis=1) == 0).sum())
    out["read_back"] = read_back
    out["crops_all_no_data"] = nodata_only
    if read_back != idx["n_crops"]:
        out["problems"].append("read back fewer crops than the index says")
    if nodata_only:
        out["problems"].append(f"{nodata_only} crops hold no data")
    out["bytes"] = sum(f.stat().st_size for f in d.iterdir())
    # the label and, while the JP2 is on disk, pixels against the source
    jp2 = config.find_strip(sid)
    lbl = root / "labels" / f"{sid}_RED.LBL"
    if not lbl.exists():
        out["problems"].append("no label copy")
    if jp2 is None:
        out["problems"].append("JP2 not on disk: pixels not compared")
        return out
    out["jp2_bytes"] = Path(jp2).stat().st_size
    if lbl.exists():
        out["label_identical"] = ex.sha256(lbl) == ex.sha256(Path(jp2).with_suffix(".LBL"))
        if not out["label_identical"]:
            out["problems"].append("label copy differs")
    strip = Strip.open(sid)
    n = idx["n_crops"]
    ranks = sorted({1, n, *[int(k) + 1 for k in rng.choice(n, size=min(SAMPLE, n), replace=False)]}) if n else []
    same = 0
    for rank in ranks:
        row = idx["rows"][rank - 1]
        size = idx["crop_size_px"]
        r0, c0 = int(round(row["row"])) - size // 2, int(round(row["col"])) - size // 2
        win = ex._clipped_read(strip, r0, r0 + size, c0, c0 + size)
        same += bool(np.array_equal(ex.cut_square(win, row["row"], row["col"], size), es.crop(rank)))
    out["pixels_compared"] = len(ranks)
    out["pixels_equal"] = same
    if same != len(ranks):
        out["problems"].append("a sampled crop differs from the JP2")
    if not np.array_equal(strip.overview.data, es.overview.data):
        out["problems"].append("overview differs from the JP2")
    return out


def check_pieces(root: Path) -> dict:
    meta = load(root / "pieces.json")
    cfg = tp.TransplantConfig(**meta["config"])
    out = {"windows": 0, "no_position": [], "cut_replays_equal": 0, "problems": [], "shams_differ_from_t1": []}
    labels: dict = {}
    for p in meta["pieces"]:
        name = f"{p['strip']}/{p['site']}/{p['piece']}{' sham' if p['sham'] else ''}"
        if p["file"] is None:
            out["no_position"].append(name)
            continue
        path = root / "pieces" / p["file"]
        if ex.sha256(path) != p["sha256"]:
            out["problems"].append(f"{name}: sha256 differs")
            continue
        win = ex.read_window(path)
        out["windows"] += 1
        sid = p["strip"]
        if sid not in labels:
            labels[sid] = Strip.open(sid)
        strip = labels[sid]
        replay = tp.cut_piece(WindowStrip(strip.label, win), p["site"], p["piece"], p["kind"], p["row"], p["col"], p["size_m"], cfg, sham=p["sham"])
        truth = tp.cut_piece(strip, p["site"], p["piece"], p["kind"], p["row"], p["col"], p["size_m"], cfg, sham=p["sham"])
        if (replay is None) != (truth is None) or (truth is not None and not np.array_equal(replay.gain, truth.gain)):
            out["problems"].append(f"{name}: the cut from the export differs from the cut from the JP2")
        else:
            out["cut_replays_equal"] += 1
        if p["sham"] and not p.get("same_as_transplant_t1"):
            out["shams_differ_from_t1"].append(name)
    return out


def check_tiles(root: Path) -> dict:
    meta = load(root / "tiles.json")
    out = {"tiles": 0, "pixels_equal": 0, "bytes": 0, "problems": []}
    for t in meta["tiles"]:
        path = root / "tiles" / t["file"]
        if ex.sha256(path) != t["sha256"]:
            out["problems"].append(f"{t['file']}: sha256 differs")
            continue
        win = ex.read_window(path)
        out["tiles"] += 1
        out["bytes"] += path.stat().st_size
        truth = Strip.open(t["strip"]).read(t["row0"], t["row1"], t["col0"], t["col1"])
        if np.array_equal(win.data, truth.data):
            out["pixels_equal"] += 1
        else:
            out["problems"].append(f"{t['file']}: differs from the JP2")
    return out


def check_lookup(root: Path, ida: str, idb: str) -> dict:
    """Persistence run on the same pair and the cached nodes with the exported strips and with the JP2 strips.
    The two must agree record for record, or the delete would change what persistence says."""
    cands = {s: json.loads(run.strip_output(SEARCH_OUT / "candidates", s).read_text())["strips"][s]["candidates"] for s in (ida, idb)}
    cache = load(rg.nodes_path(SEARCH_OUT / "registration", ida, idb))
    nodes = rg.nodes_from_json(cache["directions"][f"{ida}->{idb}"]["nodes"])
    surv = sorted(cands[ida], key=lambda c: -float(c["score"]))[:200]
    strips = Strip.open(ida), Strip.open(idb)
    radius = 8.0 * 0.25 / strips[1].label.scale_m
    reach = 8192.0 * 0.25 / strips[0].label.scale_m
    rec_x, cnt_x = sp.look_up(surv, cands[idb], ex.ExportedStrip(root, ida), ex.ExportedStrip(root, idb), nodes, radius, reach)
    rec_s, cnt_s = sp.look_up(surv, cands[idb], *strips, nodes, radius, reach)
    return {"pair": [ida, idb], "source": cache["source"], "survivors": len(surv), "counts_export": cnt_x, "counts_jp2": cnt_s, "identical": rec_x == rec_s}


def lookup_pairs() -> list[tuple[str, str]]:
    """The largest pair item 11 registered and the largest the retry registered."""
    found = {}
    for f in (SEARCH_OUT / "registration").glob("nodes_*.json"):
        d = load(f)
        if rg.is_registered([v["registration"]["ok"] for v in d["directions"].values()]):
            kind = "retry" if d["source"].startswith("12c") else "item 11"
            if kind not in found or d["km2_shared"] > found[kind]["km2_shared"]:
                found[kind] = d
    return [tuple(d["pair"]) for d in found.values()]


def nearest_target_gaps(listed: set[str]) -> list[dict]:
    """Tuning strips whose nearest search strips by sun height (the transplant's choice) are outside the listed
    tiles' strips. After the delete those pieces can only be planted into the listed strips."""
    sites, _ = controls()
    targets = tp.load_labels(tp.search_targets(sites, config.manifest_path().read_text()))
    out = []
    for sid in tp.tuning_sources(sites):
        p = config.find_strip(sid)
        if p is None:
            continue
        lbl = Strip(p).label
        near = tp.nearest_targets(lbl, targets, 4)
        out.append({"strip": sid, "tan_incidence": round(math.tan(math.radians(lbl.incidence_deg)), 3), "nearest": near,
                    "nearest_not_listed": [t for t in near if t not in listed]})
    return out


def check(a) -> int:
    root = Path(a.out)
    rng = np.random.default_rng(0)
    rows = []
    all_roles = roles()
    for sid, role in sorted(all_roles.items(), key=lambda kv: (kv[1], kv[0])):
        rows.append(check_strip(root, sid, role, a.top, rng))
        r = rows[-1]
        print(f"{sid} {role}: {r.get('exported')} of {r.get('candidates_total')}, equal {r.get('pixels_equal')}/{r.get('pixels_compared')}, {r['problems']}", flush=True)
    pieces = check_pieces(root)
    tiles = check_tiles(root)
    lookup = [check_lookup(root, *pair) for pair in lookup_pairs()]
    print(pieces, tiles, lookup, flush=True)
    listed = {t["strip"] for t in load(root / "tiles.json")["tiles"]}
    gaps = nearest_target_gaps(listed)
    search_rows = [r for r in rows if r["role"] == "search"]
    labels_all = sorted(p.name for p in (root / "labels").glob("*.LBL"))
    labels_missing = sorted({p.name for p in config.strips_dir().rglob("*.LBL")} - set(labels_all))
    result = {
        "what": "item 12c(b): what was exported per strip and whether it reads back; nothing has been deleted",
        "ok": not any(r["problems"] for r in rows) and not pieces["problems"] and not tiles["problems"] and all(k["identical"] for k in lookup)
        and tiles["tiles"] == tiles["pixels_equal"],
        "strips": rows,
        "pieces": pieces,
        "tiles": tiles,
        "lookup_from_export": lookup,
        "nearest_targets": gaps,
        "labels": {"n": len(labels_all), "names": labels_all, "on_disk_not_copied": labels_missing},
        "export_bytes": sum(f.stat().st_size for f in root.rglob("*") if f.is_file()),
        "delete_proposed": {"what": "the .JP2 of each search strip; the .LBL files, the manifest and the tuning strips stay",
                            "strips": [r["strip"] for r in search_rows], "bytes": sum(r.get("jp2_bytes", 0) for r in search_rows)},
        "free_gb_now": round(free_gb(root), 1),
        "git": run.git_state(),
    }
    (root / "check.json").write_text(json.dumps(result, indent=1))
    lines = ["| strip | role | candidates | expected | exported | read back | sampled crops equal to JP2 | label same | MB | problems |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['strip']} | {r['role']} | {r.get('candidates_total')} | {r.get('expected')} | {r.get('exported')} | {r.get('read_back')} | "
                     f"{r.get('pixels_equal')} of {r.get('pixels_compared')} | {r.get('label_identical')} | {r.get('bytes', 0) // 1000000} | {'; '.join(r['problems']) or 'none'} |")
    (root / "check.md").write_text("\n".join(lines) + "\n")
    print(f"ok={result['ok']}; written {root / 'check.json'} and check.md")
    return 0 if result["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--ids", nargs="*", default=None)
    e.add_argument("--limit", type=int, default=0)
    e.add_argument("--top", type=int, default=2000)
    e.add_argument("--size", type=int, default=320, help="crop side in native pixels; room for the vote crop's 256 and its shifts")
    e.add_argument("--min-free-gb", type=float, default=4.0)
    p = sub.add_parser("pieces")
    p.add_argument("--piece-size", type=int, default=640)
    sub.add_parser("tiles")
    sub.add_parser("labels")
    c = sub.add_parser("check")
    c.add_argument("--top", type=int, default=2000)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    return {"export": export_crops, "pieces": export_pieces, "tiles": export_tiles, "labels": export_labels, "check": check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
