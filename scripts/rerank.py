"""The learned re-ranker of docs/plan.md item 13; the protocol is docs/proposals/reranker-v1-protocol.md.

    uv run scripts/rerank.py plant               the transplant run on the listed tiles, tile by tile; rerun to resume
    uv run --group rerank scripts/rerank.py embed    per strip and per tile; rerun to resume
    uv run scripts/rerank.py fit [--variants ...] --no-texture ID ID

Reads only out/export. Writes under out/rerank. A strip of a blind site is refused. No paid model is called.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers import transplant as tp  # noqa: E402
from landers.detect import DetectorConfig, detect_tile, finish_tile, load_calibration, load_shape_rules  # noqa: E402
from landers.label import StripLabel  # noqa: E402
from landers.rerank import crops as rc  # noqa: E402
from landers.rerank import model as rm  # noqa: E402
from landers.score import match_radius_px, recall_at_false_alarm_rate, score  # noqa: E402
from landers.search import export as ex  # noqa: E402
from landers.search import run  # noqa: E402

EXPORT = config.REPO_ROOT / "out" / "export"
OUT = config.REPO_ROOT / "out" / "rerank"
RUN = OUT / "t10"
EMB = OUT / "emb"
SEED = 0
COPIES = 4
NEAREST = 4
TOP_NS = (10, 20, 50, 100, 250)
PRIMARY_N = 20
_labels: dict[str, StripLabel] = {}


def load(path) -> dict:
    return json.loads(Path(path).read_text())


def controls() -> tuple[dict, dict, dict]:
    root = config.REPO_ROOT / "controls"
    return load(root / "sites.json"), load(root / "thresholds.json"), load(root / "tuning.json")


def label_of(sid: str) -> StripLabel:
    if sid not in _labels:
        _labels[sid] = StripLabel.read(EXPORT / "labels" / f"{sid}_RED.LBL")
    return _labels[sid]


def tile_key(t: dict) -> str:
    return f"{t['strip']}:{t['row0']}:{t['col0']}"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)


def save_npz(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part.npz")
    np.savez(tmp, **arrays)
    tmp.replace(path)


def site_strips(sites: dict) -> dict[str, list[str]]:
    return {s["name"]: list(s["strips"]) for s in sites["sites"] if s["group"] == "tuning"}


# ---------------------------------------------------------------- the transplant run


def build_cuts(meta: dict, sites: dict) -> tuple[list[tp.Cut], list[str]]:
    allowed = tp.tuning_sources(sites)
    cfg = tp.TransplantConfig(**meta["config"])
    cuts, skipped = [], []
    for p in meta["pieces"]:
        name = f"{p['site']}/{p['piece']}/{p['strip']}{' sham' if p['sham'] else ''}"
        if p["strip"] not in allowed:
            raise ValueError(f"{name}: not a tuning strip")
        if p["file"] is None:
            skipped.append(f"{name}: no position")
            continue
        strip = ex.WindowStrip(label_of(p["strip"]), ex.read_window(EXPORT / "pieces" / p["file"]))
        c = tp.cut_piece(strip, p["site"], p["piece"], p["kind"], p["row"], p["col"], p["size_m"], cfg, sham=p["sham"])
        if c is None:
            skipped.append(f"{name}: could not cut")
        else:
            cuts.append(c)
    return cuts, skipped


def allocate(cuts: list[tp.Cut], tiles: list[dict], seed: int = SEED) -> tuple[dict[str, list[int]], dict[str, list[str]]]:
    """Every copy of every cut to a tile of its source's nearest listed strips. The draw is fixed before any tile runs,
    so a resumed run plants the same things."""
    rng = np.random.default_rng(seed)
    labels = {t["strip"]: label_of(t["strip"]) for t in tiles}
    targets_of: dict[str, list[str]] = {}
    per_tile: dict[str, list[int]] = {tile_key(t): [] for t in tiles}
    for ci, c in enumerate(cuts):
        if c.source not in targets_of:
            targets_of[c.source] = tp.nearest_targets(label_of(c.source), labels, NEAREST)
        choices = [tile_key(t) for t in tiles if t["strip"] in targets_of[c.source]]
        if not choices:
            continue
        order = rng.permutation(len(choices))
        for k in range(COPIES):
            per_tile[choices[int(order[k % len(choices)])]].append(ci)
    return per_tile, targets_of


def plant(a) -> int:
    sites, _, _ = controls()
    meta = load(EXPORT / "pieces.json")
    tiles = load(EXPORT / "tiles.json")["tiles"]
    cuts, skipped = build_cuts(meta, sites)
    per_tile, targets_of = allocate(cuts, tiles)
    cfg = tp.TransplantConfig(**meta["config"])
    dcfg = DetectorConfig(calibration="landers/calibration_v0.json", shape_rules="landers/shape_v3.json")
    dcfg_abs = DetectorConfig(calibration=str(config.REPO_ROOT / dcfg.calibration), shape_rules=str(config.REPO_ROOT / dcfg.shape_rules))
    cal, shape = load_calibration(dcfg_abs), load_shape_rules(dcfg_abs)
    t0 = time.time()
    (RUN / "tiles").mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(tiles):
        key = tile_key(t)
        js = RUN / "tiles" / f"{t['file'][:-4]}.json"
        if js.exists():
            continue
        lbl = label_of(t["strip"])
        win = ex.read_window(EXPORT / "tiles" / t["file"])
        rng = np.random.default_rng([SEED, i])
        idxs = list(per_tile[key])
        rng.shuffle(idxs)
        planted, placed = tp.place_in_tile(win, lbl, cuts, idxs, rng, cfg, key)
        cands = finish_tile(detect_tile(planted, lbl, dcfg_abs), dcfg_abs, cal, shape)
        ex.write_window(RUN / "tiles" / t["file"], planted.data, planted.row0, planted.col0)
        write_json(js, {
            "tile": key, "strip": t["strip"], "asked": len(idxs),
            "area_km2": float(win.valid.sum()) * lbl.scale_m**2 / 1e6,
            "placements": [p.to_json() for p in placed],
            "detections": [{"tile": key, "row": round(c.row - t["row0"], 1), "col": round(c.col - t["col0"], 1),
                            "score": round(c.score, 4), "branch": c.branch, "area_px": c.area_px} for c in cands],
        })
        print(f"{key}: {len(placed)}/{len(idxs)} planted, {len(cands)} detections, {time.time() - t0:.0f}s", flush=True)
    records = [load(RUN / "tiles" / f"{t['file'][:-4]}.json") for t in tiles]
    write_json(RUN / "run.json", {
        "what": "item 13: every recorded piece and its sham planted into the 46 listed tiles, detector at frozen-v1",
        "seed": SEED, "copies": COPIES, "nearest": NEAREST, "transplant": cfg.to_json(), "detector": dcfg.to_json(),
        "targets_of": targets_of, "cuts": [c.to_json() for c in cuts], "skipped": skipped,
        "n_placements": sum(not p["sham"] for r in records for p in r["placements"]),
        "n_sham_placements": sum(p["sham"] for r in records for p in r["placements"]),
        "asked": sum(r["asked"] for r in records), "n_detections": sum(len(r["detections"]) for r in records),
        "area_km2": sum(r["area_km2"] for r in records), "git": run.git_state(),
    })
    print(f"written {RUN / 'run.json'}; skipped {skipped}")
    return 0


# ---------------------------------------------------------------- embeddings


def strips_with_pieces(sites: dict, thresholds: dict, answers: dict) -> list[str]:
    return sorted({p["strip"] for p in tp.key_pieces(answers, thresholds, tp.tuning_sources(sites))})


def embed_rows(embedder, raws, lbl: StripLabel) -> np.ndarray:
    return embedder([rc.views(r, lbl.sub_solar_azimuth_deg, lbl.scale_m) for r in raws])


def embed(a) -> int:
    from landers.rerank.embed import MODEL, Dino

    sites, thresholds, answers = controls()
    d = Dino(str(OUT / "hf"), batch=a.batch)
    t0 = time.time()
    EMB.mkdir(parents=True, exist_ok=True)
    print(f"{MODEL} at {d.revision} on {d.device}", flush=True)

    if not (EMB / "pieces.npz").exists():
        rows = [p for p in load(EXPORT / "pieces.json")["pieces"] if not p["sham"] and p["file"]]
        out = []
        for p in rows:
            win = ex.read_window(EXPORT / "pieces" / p["file"])
            raw = rc.cut(win.data, win.row0, win.col0, p["row"], p["col"])
            out.append(embed_rows(d, [raw], label_of(p["strip"])))
        save_npz(EMB / "pieces.npz", emb=np.concatenate(out).astype(np.float32))
        print(f"pieces: {len(rows)} crops, {time.time() - t0:.0f}s", flush=True)

    for sid in strips_with_pieces(sites, thresholds, answers):
        ex.refuse_blind(sites, sid)
        path = EMB / f"strip_{sid}.npz"
        if path.exists():
            continue
        es = ex.ExportedStrip(EXPORT, sid)
        lbl = label_of(sid)
        out = []
        for ch in es.index["chunks"]:
            with np.load(EXPORT / "strips" / sid / ch["file"]) as z:
                stack = ex.join_bytes(z["low"], z["high"])
            out.append(embed_rows(d, list(stack), lbl))
            print(f"{sid}: {ch['first_rank'] + ch['n'] - 1} crops, {time.time() - t0:.0f}s", flush=True)
        save_npz(path, emb=np.concatenate(out).astype(np.float32))

    for t in load(EXPORT / "tiles.json")["tiles"]:
        path = EMB / f"tile_{t['file']}"
        if path.exists():
            continue
        rec = load(RUN / "tiles" / f"{t['file'][:-4]}.json")
        win = ex.read_window(RUN / "tiles" / t["file"])
        lbl = label_of(t["strip"])
        pts = [(x["row"], x["col"]) for x in rec["detections"]] + [(x["row"], x["col"]) for x in rec["placements"]]
        out = []
        for i in range(0, len(pts), 64):
            # row and col in a tile record are tile-local
            raws = [rc.cut(win.data, 0, 0, r, c) for r, c in pts[i : i + 64]]
            out.append(embed_rows(d, raws, lbl))
        emb = np.concatenate(out).astype(np.float32) if out else np.zeros((0, 1536), np.float32)
        n = len(rec["detections"])
        save_npz(path, det=emb[:n], placement=emb[n:])
        print(f"{tile_key(t)}: {len(pts)} crops, {time.time() - t0:.0f}s", flush=True)
    write_json(OUT / "encoder.json", {"model": MODEL, "revision": d.revision, "device": d.device, "batch": a.batch,
                                      "crops_last_pass": d.crops, "seconds_last_pass": round(time.time() - t0)})
    print(f"done: {d.crops} crops this pass, {time.time() - t0:.0f}s", flush=True)
    return 0


# ---------------------------------------------------------------- the table every fold reads


class Table:
    """One row per crop the folds use. ``source`` is native, copy, list_fa, sham, tile_fa, or "" for a row that only gets
    scored. ``site`` is the site a row leaves with ("" for one that leaves with none); ``target`` the planted strip."""

    def __init__(self):
        self.emb, self.score, self.nov, self.source, self.site, self.target = [], [], [], [], [], []
        self.n = 0

    def add(self, emb, score, nov, source, site, target) -> np.ndarray:
        k = len(emb)
        self.emb.append(emb)
        self.score.append(np.asarray(score, np.float64))
        self.nov.append(np.asarray(nov, np.float64))
        self.source.append(np.array(source if isinstance(source, list) else [source] * k, dtype=object))
        self.site.append(np.array(site if isinstance(site, list) else [site] * k, dtype=object))
        self.target.append(np.array([target] * k, dtype=object))
        idx = np.arange(self.n, self.n + k)
        self.n += k
        return idx

    def freeze(self) -> None:
        self.emb = np.concatenate(self.emb)
        self.score, self.nov = np.concatenate(self.score), np.concatenate(self.nov)
        self.source = np.concatenate(self.source).astype(str)
        self.site = np.concatenate(self.site).astype(str)
        self.target = np.concatenate(self.target).astype(str)


def add_lists(tb: Table, pieces: list[dict], sites: dict, thresholds: dict) -> tuple[dict, dict]:
    by_strip: dict[str, list[dict]] = {}
    for p in pieces:
        by_strip.setdefault(p["strip"], []).append(p)
    meta = [p for p in load(EXPORT / "pieces.json")["pieces"] if not p["sham"] and p["file"]]
    with np.load(EMB / "pieces.npz") as z:
        piece_emb = z["emb"]
    piece_row = {(p["site"], p["piece"], p["strip"]): piece_emb[i] for i, p in enumerate(meta)}
    site_of = {sid: name for name, strips in site_strips(sites).items() for sid in strips}
    lists: dict[str, dict] = {}
    native_row: dict[int, int] = {}
    for sid, plist in sorted(by_strip.items()):
        rows = ex.ExportedStrip(EXPORT, sid).index["rows"]
        scale = label_of(sid).scale_m
        with np.load(EMB / f"strip_{sid}.npz") as z:
            emb = z["emb"]
        rr, cc = np.array([x["row"] for x in rows]), np.array([x["col"] for x in rows])
        sc = np.array([x["score"] for x in rows], np.float64)
        zone = np.zeros(len(rows), bool)
        best_of: dict[int, int] = {}
        for p in plist:
            d = np.hypot(rr - p["row"], cc - p["col"])
            radius = match_radius_px(thresholds, scale, p["kind"])
            zone |= d <= max(radius, p["size_m"] / scale)
            inside = np.flatnonzero(d <= radius)
            if len(inside):
                best_of[p["index"]] = int(inside[0])  # rows are best first
        source = [("list_fa" if i < rm.TOP_NEGATIVES and not zone[i] else "") for i in range(len(rows))]
        for j in best_of.values():
            source[j] = "native"
        idx = tb.add(emb, sc, rm.novelty(emb), source, site_of[sid], "")
        lists[sid] = {"rows": rows, "idx": idx, "site": site_of[sid]}
        for p in plist:
            if p["index"] in best_of:
                native_row[p["index"]] = int(idx[best_of[p["index"]]])
            else:
                # below the top 2,000 or never listed: the crop at the recorded position, scored at the list's floor
                e = piece_row[(p["site"], p["piece"], p["strip"])][None]
                native_row[p["index"]] = int(tb.add(e, [float(sc.min())], rm.novelty(emb, query=e), "native", p["site"], "")[0])
    return lists, native_row


def add_tiles(tb: Table, pieces: list[dict], thresholds: dict) -> tuple[list, list, list, dict]:
    recs: dict[str, list[dict]] = {}
    for t in load(EXPORT / "tiles.json")["tiles"]:
        r = load(RUN / "tiles" / f"{t['file'][:-4]}.json")
        with np.load(EMB / f"tile_{t['file']}") as z:
            r["det_emb"], r["pl_emb"] = z["det"], z["placement"]
        recs.setdefault(t["strip"], []).append(r)
    cuts = load(RUN / "run.json")["cuts"]
    piece_index = {(p["site"], p["piece"], p["strip"]): p["index"] for p in pieces}
    detections, truths, shams = [], [], []
    copies_of: dict[int, list[int]] = {}
    for tid, rs in sorted(recs.items()):
        pop = np.concatenate([r["det_emb"] for r in rs])
        pop_nov = rm.novelty(pop)
        floor = min((float(d["score"]) for r in rs for d in r["detections"]), default=-3.0)
        offset = 0
        for r in rs:
            dets, pls = r["detections"], r["placements"]
            n = len(dets)
            radii = [match_radius_px(thresholds, cuts[p["cut_index"]]["scale_m"], p["kind"]) for p in pls]
            source, site, best = rm.label_tile(dets, pls, radii)
            idx = tb.add(r["det_emb"], [d["score"] for d in dets], pop_nov[offset : offset + n], source, site, tid)
            offset += n
            for j, d in enumerate(dets):
                detections.append({**d, "row_index": int(idx[j])})
            for k, p in enumerate(pls):
                cut = cuts[p["cut_index"]]
                e = r["pl_emb"][k][None]
                nov_c = rm.novelty(pop, query=e)
                if p["sham"]:
                    s = float(dets[best[k]]["score"]) if best[k] is not None else floor
                    shams.append({"row_index": int(tb.add(e, [s], nov_c, "sham", p["site"], tid)[0]), "site": p["site"]})
                    continue
                i_row = int(idx[best[k]]) if best[k] is not None else int(tb.add(e, [floor], nov_c, "copy", p["site"], tid)[0])
                truths.append({"tile": p["tile"], "row": p["row"], "col": p["col"], "kind": p["kind"], "site": p["site"], "piece": p["piece"],
                               "size_m": cut["size_m"], "radius_px": radii[k], "target": tid, "row_index": i_row})
                copies_of.setdefault(piece_index[(p["site"], p["piece"], cut["source"])], []).append(i_row)
    return detections, truths, shams, copies_of


def build_table(sites: dict, thresholds: dict, answers: dict) -> dict:
    tb = Table()
    pieces = tp.key_pieces(answers, thresholds, tp.tuning_sources(sites))
    for i, p in enumerate(pieces):
        p["index"] = i
    lists, native_row = add_lists(tb, pieces, sites, thresholds)
    detections, truths, shams, copies_of = add_tiles(tb, pieces, thresholds)
    tb.freeze()
    return {"table": tb, "pieces": pieces, "lists": lists, "native_row": native_row, "detections": detections, "truths": truths,
            "shams": shams, "copies_of": copies_of}


# ---------------------------------------------------------------- the boards


def key_ranks(rows_by_strip: dict[str, list[dict]], answers: dict, thresholds: dict) -> dict[str, int | None]:
    """site/piece/strip -> rank by landers.score, for the lists given."""
    cands = {"strips": {sid: {"candidates": rows, "scale_m": label_of(sid).scale_m, "valid_area_km2": 0.0} for sid, rows in rows_by_strip.items()}}
    return {f"{p.site}/{p.piece}/{p.strip}": p.rank for p in score(cands, answers, thresholds).pieces if p.strip in rows_by_strip}


def curve(ranks) -> dict[str, int]:
    return {str(n): sum(r is not None and r <= n for r in ranks) for n in TOP_NS}


def kind_curve(keyed: dict, pieces: list[dict]) -> dict:
    kinds = {f"{p['site']}/{p['piece']}/{p['strip']}": p["kind"] for p in pieces}
    out: dict = {}
    for k, v in keyed.items():
        out.setdefault(kinds[k], []).append(v)
    return {k: {"n": len(v), **curve(v)} for k, v in sorted(out.items())}


def site_curve(keyed: dict) -> dict:
    out: dict = {}
    for k, v in keyed.items():
        d = out.setdefault(k.split("/")[0], {"n": 0, "found": 0})
        d["n"] += 1
        d["found"] += int(v is not None and v <= PRIMARY_N)
    return out


def transplant_rows(dets: list[dict], truths: list[dict], area: float, fa: float, no_texture: set[str]) -> list[dict]:
    """Found per kind, site and kind of ground at this false-alarm rate."""
    def group(t):
        return t["kind"], f"{t['site']}|{'no_texture' if t['target'] in no_texture else 'texture'}"

    r = recall_at_false_alarm_rate(dets, truths, area, 20.0, fa, group=group)
    return [{"kind": x["kind"], "site": x["size_bin"].split("|")[0], "ground": x["size_bin"].split("|")[1], "n": x["n"], "found": x["found"]} for x in r["rows"]]


def summarise(rows: list[dict]) -> dict:
    out: dict = {"n": 0, "found": 0, "by_kind": {}, "by_site": {}, "by_ground": {}}
    for x in rows:
        out["n"] += x["n"]
        out["found"] += x["found"]
        for name in ("kind", "site", "ground"):
            d = out[f"by_{name}"].setdefault(x[name], {"n": 0, "found": 0})
            d["n"] += x["n"]
            d["found"] += x["found"]
    out["interval_95"] = rm.wilson(out["found"], out["n"])
    return out


def spread(by_site: dict) -> dict:
    vals = [d["found"] / d["n"] for d in by_site.values() if d["n"]]
    return {"sites": len(vals), "mean": round(statistics.mean(vals), 3), "sd": round(statistics.stdev(vals), 3), "min": round(min(vals), 3), "max": round(max(vals), 3)}


def target_areas(target_ids: list[str]) -> dict[str, float]:
    out = {}
    for sid in target_ids:
        es = ex.ExportedStrip(EXPORT, sid)
        out[sid] = round(float(es.overview.valid.sum()) * (es.overview_step * es.label.scale_m) ** 2 / 1e6, 2)
    return out


def fold(tb: Table, t: dict, site: str, strips: list[str], targets: list[str], variant: str, answers: dict, thresholds: dict, rate_list: list, area: float, no_texture: set[str]) -> dict:
    """One site held out: its lists re-ordered, every detection re-scored by the model without its own target strip."""
    use = rm.VARIANTS[variant]
    pos = rm.is_positive(tb.source)

    def fitted(held_target):
        mask = rm.training_mask(tb.source, tb.site, tb.target, site, held_target, use["transplanted"])
        return rm.fit(tb.emb[mask], tb.score[mask], tb.nov[mask], pos[mask].astype(float), rm.source_weights(tb.source[mask]), variant)

    m = fitted(None)
    held = (tb.target == "") & (tb.site == site)
    off = np.zeros(tb.n)
    off[held] = m.decision(tb.emb[held], tb.score[held], tb.nov[held])
    lists = {sid: [{**x, "score": float(off[i])} for x, i in zip(t["lists"][sid]["rows"], t["lists"][sid]["idx"], strict=True)] for sid in strips if sid in t["lists"]}
    ranks = key_ranks(lists, {**answers, "sites": [s for s in answers["sites"] if s["name"] == site]}, thresholds)
    on = np.zeros(tb.n)
    for tid in targets:
        mt = fitted(tid)
        sel = tb.target == tid
        on[sel] = mt.decision(tb.emb[sel], tb.score[sel], tb.nov[sel])
    dets = [{**d, "score": float(on[d["row_index"]])} for d in t["detections"]]
    found = {name: [x for x in transplant_rows(dets, t["truths"], area, fa, no_texture) if x["site"] == site] for name, fa in rate_list}
    paste = []
    for p in t["pieces"]:
        if p["site"] == site:
            rows = t["copies_of"].get(p["index"], [])
            paste.append({"site": site, "piece": p["piece"], "strip": p["strip"], "kind": p["kind"], "native": round(float(off[t["native_row"][p["index"]]]), 3),
                          "copies_median": round(float(np.median(on[rows])), 3) if rows else None, "copies": len(rows)})
    real = np.array([x["row_index"] for x in t["truths"] if x["site"] == site], int)
    sham = np.array([x["row_index"] for x in t["shams"] if x["site"] == site], int)
    fas = np.flatnonzero((tb.source == "tile_fa") & (tb.target != ""))
    return {"ranks": ranks, "found": found, "paste": paste, "real_over_sham": rm.auc(on[real], on[sham]), "sham_over_fa": rm.auc(on[sham], on[fas])}


def fit_folds(a) -> int:
    sites, thresholds, answers = controls()
    t = build_table(sites, thresholds, answers)
    tb: Table = t["table"]
    groups = site_strips(sites)
    targets = sorted({str(v) for v in tb.target if v})
    area = float(load(RUN / "run.json")["area_km2"])
    areas = target_areas(targets)
    median_km2 = statistics.median(areas.values())
    rate_list = [(f"N{n}", n / median_km2) for n in TOP_NS] + [("board_rate", float(thresholds["pass"]["max_false_alarms_per_km2"]))]
    no_texture = set(a.no_texture)
    counts = {str(k): int(v) for k, v in zip(*np.unique(tb.source, return_counts=True), strict=True)}
    print(f"{tb.n} rows, {counts}, {len(targets)} target strips, {area:.2f} km2 planted", flush=True)

    frozen_ranks = key_ranks({sid: e["rows"] for sid, e in t["lists"].items()}, answers, thresholds)
    frozen_tp = {name: summarise(transplant_rows(t["detections"], t["truths"], area, fa, no_texture)) for name, fa in rate_list}
    frozen = {"key_ranks": frozen_ranks, "key_curve": curve(frozen_ranks.values()), "key_kinds": kind_curve(frozen_ranks, t["pieces"]), "key_by_site": site_curve(frozen_ranks),
              "key_spread_at_20": spread(site_curve(frozen_ranks)), "transplant": frozen_tp, "transplant_spread_at_20": spread(frozen_tp[f"N{PRIMARY_N}"]["by_site"])}
    base = {"protocol": "docs/proposals/reranker-v1-protocol.md", "encoder": load(OUT / "encoder.json"), "git": run.git_state(), "rows": counts,
            "target_strip_km2": areas, "median_target_km2": median_km2, "planted_km2": area, "rates_per_km2": dict(rate_list), "no_texture": sorted(no_texture),
            "not_blind": "every number here is on tuning sites; the four sealed for frozen-v1 are not blind"}

    for variant in a.variants:
        t0 = time.time()
        ranks: dict = {}
        found: dict[str, list] = {name: [] for name, _ in rate_list}
        paste, real_auc, sham_auc = [], {}, {}
        for site, strips in groups.items():
            f = fold(tb, t, site, strips, targets, variant, answers, thresholds, rate_list, area, no_texture)
            ranks.update(f["ranks"])
            for name in found:
                found[name] += f["found"][name]
            paste += f["paste"]
            real_auc[site], sham_auc[site] = f["real_over_sham"], f["sham_over_fa"]
            print(f"{variant} {site}: {time.time() - t0:.0f}s", flush=True)
        tp_summary = {name: summarise(rows) for name, rows in found.items()}
        key_curve = curve(ranks.values())
        n_key = len(ranks)
        dropped = sorted(k for k, v in frozen_ranks.items() if v is not None and v <= PRIMARY_N and not (ranks.get(k) is not None and ranks[k] <= PRIMARY_N))
        paste_v = rm.paste_verdict(paste)
        at = str(PRIMARY_N)
        key_win = key_curve[at] > frozen["key_curve"][at]
        tp_win = tp_summary[f"N{at}"]["found"] > frozen_tp[f"N{at}"]["found"]
        res = {**base, "variant": variant, "frozen_v1": frozen, "key_ranks": ranks, "key_curve": key_curve, "key_n": n_key,
               "key_interval_95_at_20": rm.wilson(key_curve[at], n_key), "frozen_key_interval_95_at_20": rm.wilson(frozen["key_curve"][at], n_key),
               "key_kinds": kind_curve(ranks, t["pieces"]), "key_by_site": site_curve(ranks), "key_spread_at_20": spread(site_curve(ranks)),
               "transplant": tp_summary, "transplant_spread_at_20": spread(tp_summary[f"N{at}"]["by_site"]), "dropped_from_top_20": dropped,
               "paste_rows": paste, "paste": paste_v, "auc_real_over_sham": real_auc, "auc_sham_over_tile_fa": sham_auc, "seconds": round(time.time() - t0),
               "rule": {"key_beats": key_win, "transplant_beats": tp_win, "no_piece_dropped": not dropped, "not_learning_the_paste": paste_v["learning_the_paste"] is False,
                        "met": bool(key_win and tp_win and not dropped and paste_v["learning_the_paste"] is False)}}
        write_json(OUT / "fit" / f"{variant}.json", res)
        print(f"{variant}: key {key_curve} (frozen-v1 {frozen['key_curve']}) of {n_key}; transplant at N20 {tp_summary[f'N{at}']['found']} of {tp_summary[f'N{at}']['n']} "
              f"(frozen-v1 {frozen_tp[f'N{at}']['found']}); dropped {dropped}; paste {paste_v}; rule {res['rule']}", flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plant")
    e = sub.add_parser("embed")
    e.add_argument("--batch", type=int, default=16)
    f = sub.add_parser("fit")
    f.add_argument("--variants", nargs="*", default=["primary"], choices=list(rm.VARIANTS))
    f.add_argument("--no-texture", nargs="*", default=[], help="target strips with no ground texture, reported apart")
    a = ap.parse_args(argv)
    return {"plant": plant, "embed": embed, "fit": fit_folds}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
