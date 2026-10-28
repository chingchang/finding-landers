"""The number the project is judged on.

A *candidates file* is what a detector run writes (``out/candidates_<run>.json``)::

    {"run": "...", "detector": {"version": "...", "frozen": false, ...},
     "strips": {"<observation id>": {"valid_area_km2": 31.2,
                                     "candidates": [{"row": 0-based, "col": 0-based, "score": float,
                                                     "branch": "bright|shadow|dark|persist", "grade": "..."}]}}}

An *answer key* is ``controls/tuning.json`` (or, for a person running the held-out evaluation,
``controls/heldout.json``): per site, per piece, the PDS line/sample recorded by a person.

A *thresholds file* (``controls/thresholds.json``, owned by a person) holds::

    {"match_radius_px": 20, "top_n": 20, "pass": {"min_recall_at_n": 0.8, "max_false_alarms_per_km2": 2.0}}

The score, per piece: rank of the first candidate within ``match_radius_px`` of the recorded position when
candidates are sorted by score (descending), or null; and the branch that produced it. Per strip: candidates
not within the radius of any recorded piece, divided by the strip's valid area. Headline: recall at N (the
fraction of recorded pieces with rank <= top_n) and the median false alarms per km2 over scored strips.
Pieces whose position is null are "not recorded" and are excluded from recall, never counted as misses.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path


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
    radius = float(thresholds["match_radius_px"])
    top_n = int(thresholds["top_n"])
    strips = candidates.get("strips", {})
    pieces: list[PieceResult] = []
    skipped: list[str] = []
    truth_by_strip: dict[str, list[tuple[float, float]]] = {}

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
