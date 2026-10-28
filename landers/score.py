"""The number the project is judged on.

A *candidates file* is what a detector run writes (``out/candidates_<run>.json``)::

    {"run": "...", "detector": {"version": "...", "frozen": false, ...},
     "strips": {"<observation id>": {"valid_area_km2": 31.2, "scale_m": 0.25,
                                     "candidates": [{"row": 0-based, "col": 0-based, "score": float,
                                                     "branch": "bright|shadow|sheet|dark_compact|dark",
                                                     "grade": "..."}]}}}

An *answer key* is ``controls/tuning.json`` (or, for a person running the held-out evaluation,
``controls/heldout.json``): per site, per piece, the PDS line/sample recorded by a person.

A *thresholds file* (``controls/thresholds.json``, owned by a person) holds::

    {"match_radius_m": 5.0, "top_n": 20, "pass": {"min_recall_at_n": 0.8, "max_false_alarms_per_km2": 2.0}}

The match radius is in metres and becomes pixels through each strip's MAP_SCALE, so 50 cm/px strips are
scored the same way. The score, per piece: rank of the first candidate within the radius of the recorded
position when candidates are sorted by score (descending), or null; and the branch that produced it. Per
strip: candidates not within the radius of any recorded piece, divided by the strip's valid area. Headline:
recall at N (the fraction of recorded pieces with rank <= top_n) and the median false alarms per km2 over
scored strips. Pieces whose position is null are "not recorded" and are excluded from recall, never counted
as misses.

``recall_at_false_alarm_rate`` is the injection score: with synthetic objects of known size placed in real
tiles, it finds the score threshold that keeps false alarms at the allowed rate and reports recall by kind,
size bin and branch at that threshold.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_SCALE_M = 0.25


def match_radius_px(thresholds: dict, scale_m: float) -> float:
    if "match_radius_m" in thresholds:
        return float(thresholds["match_radius_m"]) / float(scale_m)
    return float(thresholds["match_radius_px"])


@dataclass
class PieceResult:
    site: str
    piece: str
    strip: str
    rank: int | None
    branch: str | None
    distance_px: float | None


@dataclass
class StripResult:
    strip: str
    n_candidates: int
    n_true_hits: int
    false_alarms: int
    valid_area_km2: float
    false_alarms_per_km2: float | None


@dataclass
class Score:
    recall_at_n: float | None
    top_n: int
    n_pieces_recorded: int
    n_pieces_found: int
    median_false_alarms_per_km2: float | None
    passed: bool | None
    pieces: list[PieceResult]
    strips: list[StripResult]
    skipped: list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)


def _sorted_candidates(strip_entry: dict) -> list[dict]:
    return sorted(strip_entry.get("candidates", []), key=lambda c: -float(c.get("score", 0.0)))


def score(candidates: dict, answers: dict, thresholds: dict) -> Score:
    top_n = int(thresholds["top_n"])
    strips = candidates.get("strips", {})
    pieces: list[PieceResult] = []
    skipped: list[str] = []
    truth_by_strip: dict[str, list[tuple[float, float]]] = {}

    def radius_for(sid: str) -> float:
        return match_radius_px(thresholds, strips.get(sid, {}).get("scale_m", DEFAULT_SCALE_M))

    for site in answers["sites"]:
        for pc in site["pieces"]:
            if pc.get("line") is None or pc.get("sample") is None or pc.get("strip") is None:
                skipped.append(f"{site['name']}/{pc['piece']}: position not recorded")
                continue
            sid = pc["strip"]
            row, col = float(pc["line"]) - 1.0, float(pc["sample"]) - 1.0
            truth_by_strip.setdefault(sid, []).append((row, col))
            if sid not in strips:
                skipped.append(f"{site['name']}/{pc['piece']}: strip {sid} not in this run")
                pieces.append(PieceResult(site["name"], pc["piece"], sid, None, None, None))
                continue
            radius = radius_for(sid)
            rank = branch = dist = None
            for i, c in enumerate(_sorted_candidates(strips[sid]), start=1):
                d = math.hypot(float(c["row"]) - row, float(c["col"]) - col)
                if d <= radius:
                    rank, branch, dist = i, c.get("branch"), d
                    break
            pieces.append(PieceResult(site["name"], pc["piece"], sid, rank, branch, dist))

    strip_results: list[StripResult] = []
    for sid, entry in strips.items():
        cands = entry.get("candidates", [])
        truths = truth_by_strip.get(sid, [])
        radius = radius_for(sid)
        hits = sum(
            1 for c in cands if any(math.hypot(float(c["row"]) - r, float(c["col"]) - k) <= radius for r, k in truths)
        )
        area = float(entry.get("valid_area_km2") or 0.0)
        fa = len(cands) - hits
        strip_results.append(StripResult(sid, len(cands), hits, fa, area, (fa / area) if area > 0 else None))

    scored = [p for p in pieces if p.strip in strips]
    found = [p for p in scored if p.rank is not None and p.rank <= top_n]
    recall = (len(found) / len(scored)) if scored else None
    fas = [s.false_alarms_per_km2 for s in strip_results if s.false_alarms_per_km2 is not None]
    med_fa = statistics.median(fas) if fas else None
    passed = None
    if recall is not None and med_fa is not None and "pass" in thresholds:
        p = thresholds["pass"]
        passed = recall >= float(p["min_recall_at_n"]) and med_fa <= float(p["max_false_alarms_per_km2"])
    return Score(recall, top_n, len(scored), len(found), med_fa, passed, pieces, strip_results, skipped)


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def format_report(s: Score) -> str:
    lines = []
    r = "n/a" if s.recall_at_n is None else f"{s.recall_at_n:.2f}"
    fa = "n/a" if s.median_false_alarms_per_km2 is None else f"{s.median_false_alarms_per_km2:.2f}"
    verdict = {None: "not decidable", True: "PASS", False: "FAIL"}[s.passed]
    lines.append(
        f"recall@{s.top_n} = {r} ({s.n_pieces_found}/{s.n_pieces_recorded} recorded pieces)   "
        f"median false alarms/km2 = {fa}   {verdict}"
    )
    lines.append("")
    lines.append(f"{'site':14s} {'piece':14s} {'rank':>5s} {'dist px':>8s}  branch")
    for p in s.pieces:
        rank = "-" if p.rank is None else str(p.rank)
        dist = "-" if p.distance_px is None else f"{p.distance_px:.1f}"
        lines.append(f"{p.site:14s} {p.piece:14s} {rank:>5s} {dist:>8s}  {p.branch or '-'}")
    lines.append("")
    lines.append(f"{'strip':16s} {'cands':>6s} {'hits':>5s} {'false':>6s} {'km2':>7s} {'FA/km2':>7s}")
    for t in s.strips:
        fa_s = "-" if t.false_alarms_per_km2 is None else f"{t.false_alarms_per_km2:.2f}"
        row = f"{t.strip:16s} {t.n_candidates:6d} {t.n_true_hits:5d} {t.false_alarms:6d}"
        lines.append(f"{row} {t.valid_area_km2:7.1f} {fa_s:>7s}")
    if s.skipped:
        lines.append("")
        lines.append("not scored:")
        lines.extend(f"  {x}" for x in s.skipped)
    return "\n".join(lines)


# ---------------------------------------------------------------- injection score

SIZE_BINS_M = {
    "sheet": [(8, 12), (12, 18), (18, 25)],
    "dark_compact": [(1, 2), (2, 3), (3, 4)],
    "blob_shadow": [(1, 2), (2, 3), (3, 5)],
}


def _bin_of(kind: str, size_m: float) -> str:
    for lo, hi in SIZE_BINS_M.get(kind, []):
        if lo <= size_m < hi or (size_m == hi and hi == SIZE_BINS_M[kind][-1][1]):
            return f"{lo}-{hi} m"
    return "other"


def recall_at_false_alarm_rate(
    detections: list[dict], truths: list[dict], area_km2: float, radius_px: float, fa_per_km2: float
) -> dict:
    """``detections``: candidates with ``tile``, ``row``, ``col``, ``score``, ``branch`` (tile-local
    coordinates). ``truths``: injected objects with ``tile``, ``row``, ``col``, ``kind``, ``size_m``.
    Finds the score threshold that keeps unmatched detections at or under ``fa_per_km2 * area_km2`` and
    reports recall at that threshold by kind, size bin and the branch that found each object."""
    by_tile: dict = {}
    for t in truths:
        by_tile.setdefault(t["tile"], []).append(t)

    def matches(d: dict):
        return [
            t
            for t in by_tile.get(d["tile"], [])
            if math.hypot(float(d["row"]) - float(t["row"]), float(d["col"]) - float(t["col"])) <= radius_px
        ]

    dets = sorted(detections, key=lambda d: -float(d["score"]))
    allowed = int(math.floor(fa_per_km2 * area_km2))
    threshold = -math.inf
    n_fa = 0
    for d in dets:
        if not matches(d):
            n_fa += 1
            if n_fa > allowed:
                threshold = float(d["score"])
                break
    kept = [d for d in dets if float(d["score"]) > threshold]
    fa_kept = sum(1 for d in kept if not matches(d))

    per: dict[str, dict] = {}
    for t in truths:
        key = (t["kind"], _bin_of(t["kind"], float(t["size_m"])))
        slot = per.setdefault(
            f"{key[0]} {key[1]}", {"kind": key[0], "bin": key[1], "n": 0, "found": 0, "branches": Counter()}
        )
        slot["n"] += 1
        best = None
        for d in kept:
            if d["tile"] != t["tile"]:
                continue
            if math.hypot(float(d["row"]) - float(t["row"]), float(d["col"]) - float(t["col"])) <= radius_px:
                if best is None or float(d["score"]) > float(best["score"]):
                    best = d
        if best is not None:
            slot["found"] += 1
            slot["branches"][best["branch"]] += 1
    rows = []
    for k in sorted(per):
        s = per[k]
        rows.append(
            {
                "kind": s["kind"],
                "size_bin": s["bin"],
                "n": s["n"],
                "found": s["found"],
                "recall": round(s["found"] / s["n"], 3) if s["n"] else None,
                "branches": dict(s["branches"]),
            }
        )
    total_n = sum(r["n"] for r in rows)
    total_found = sum(r["found"] for r in rows)
    return {
        "fa_per_km2_target": fa_per_km2,
        "area_km2": round(area_km2, 4),
        "false_alarms_allowed": allowed,
        "score_threshold": None if threshold == -math.inf else round(threshold, 3),
        "detections_kept": len(kept),
        "false_alarms_kept": fa_kept,
        "false_alarms_per_km2": round(fa_kept / area_km2, 3) if area_km2 > 0 else None,
        "recall_overall": round(total_found / total_n, 3) if total_n else None,
        "rows": rows,
    }


def format_injection_report(r: dict) -> str:
    lines = [
        f"false alarms allowed {r['false_alarms_allowed']} over {r['area_km2']:.3f} km2 "
        f"(target {r['fa_per_km2_target']}/km2); score threshold {r['score_threshold']}; "
        f"kept {r['detections_kept']} detections, {r['false_alarms_kept']} false "
        f"({r['false_alarms_per_km2']}/km2); recall overall {r['recall_overall']}",
        "",
        f"{'kind':14s} {'size':10s} {'n':>4s} {'found':>6s} {'recall':>7s}  branches",
    ]
    for row in r["rows"]:
        rec = "-" if row["recall"] is None else f"{row['recall']:.2f}"
        br = ", ".join(f"{b}={n}" for b, n in sorted(row["branches"].items(), key=lambda x: -x[1])) or "-"
        lines.append(f"{row['kind']:14s} {row['size_bin']:10s} {row['n']:4d} {row['found']:6d} {rec:>7s}  {br}")
    return "\n".join(lines)
