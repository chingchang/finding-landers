"""Reading the results files into one case.

Files, all written by other stages (the board writes none of them):

- the candidates file of a detector run, ``out/<run>/candidates_<run>.json`` (required);
- persistence files beside it, ``persist_<name>.json``: each direction carries the annotated candidates of
  its ``from`` strip with ``extra.persist`` and the grade after persistence;
- the model files under ``out/models/``: ``sam_<strip>.json``, ``votes_<strip>.json``,
  ``probe_<strip>.json``, ``review_<strip>.json``, ``manifest_<strip>.json`` and ``ledger.json``;
- a coverage map, ``out/search/coverage.json`` (any shape; rendered as it is);
- a score file from ``scripts/score.py`` (optional; it names sites and pieces, so the blind board drops it).

Candidate ids follow the model scripts: ``c000``, ``c001``, ... by rank in the score-sorted list of the
candidates file, the order ``landers.models.run.top_candidates`` uses. The manifest, when present, is
checked against that order and a mismatch is reported on the page, never silently joined.

A grade can be lowered by a later stage and never raised; the loader records the chain of grades a
candidate went through and flags any file that raised one. Every grade, outcome, vote and action read from a
file is checked against the fixed vocabulary; a word outside it stops the build.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from landers.halfcal import BELOW_FIELD, RATE_FIELD
from landers.models.run import candidate_id

GRADES = ("candidate", "needs second look", "likely natural")  # best to worst
NOT_ASSESSED = "not assessed"
ALL_GRADES = GRADES + (NOT_ASSESSED,)
OUTCOMES = ("pass", "fail", "unsure", "not run")
VOTE_VERDICTS = ("hardware", "natural", "unsure")
ACTIONS = ("keep", "lower")
STAGES = ("detector", "persistence", "votes", "review")
SHAPE_FEATURES = (
    "circularity",
    "fill",
    "elongation",
    "edge_sharpness",
    "shadow_alignment",
    "shadow_len_px",
    "height_m",
    "raw_score",
    "tile_rank",
)
SAM_MEASUREMENTS = (
    "equiv_diameter_m",
    "major_m",
    "minor_m",
    "elongation",
    "fill",
    "circularity",
    "edge_contrast",
    "touches_box_edge",
    "area_px",
)


class VocabularyError(ValueError):
    """A results file uses a word outside the fixed vocabulary."""


class JoinError(ValueError):
    """The files do not describe the same candidates."""


_MISSING = object()  # walk() raises
_ABSENT = object()  # has() answers False


def fmt_path(parts: tuple) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out


@dataclass(frozen=True)
class Ref:
    """A value with the file and path it was read from. ``op`` is empty when copied, ``count`` (or
    ``count where ...``) when it is the length of the list at ``path``."""

    value: Any
    source: str
    path: tuple
    op: str = ""

    @property
    def path_text(self) -> str:
        return fmt_path(self.path)


@dataclass
class Source:
    key: str
    path: Path
    data: Any
    sha256: str

    @classmethod
    def read(cls, key: str, path: Path) -> Source:
        raw = Path(path).read_bytes()
        return cls(key, Path(path), json.loads(raw), hashlib.sha256(raw).hexdigest())

    def walk(self, parts: tuple, default=_MISSING):
        cur = self.data
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            elif isinstance(cur, list) and isinstance(p, int) and -len(cur) <= p < len(cur):
                cur = cur[p]
            else:
                if default is _MISSING:
                    raise KeyError(f"{self.key}: no {fmt_path(parts)}")
                return default
        return cur

    def get(self, *parts) -> Ref | None:
        """The value at ``parts`` as a Ref, or None when the file has no such path."""
        v = self.walk(parts, None)
        return None if v is None else Ref(v, self.key, parts)

    def has(self, *parts) -> bool:
        return self.walk(parts, _ABSENT) is not _ABSENT

    def count(self, *parts, where: str = "", n: int | None = None) -> Ref:
        """The number of entries of the list (or dict) at ``parts``; with ``where`` and ``n``, the number
        of them that satisfy the stated condition, counted by the caller."""
        obj = self.walk(parts, [])
        total = len(obj)
        if where:
            if n is None or n > total:
                raise ValueError("a filtered count needs n <= the list length")
            return Ref(n, self.key, parts, f"count where {where}")
        return Ref(total, self.key, parts, "count")


def _check(value, allowed: tuple, what: str, ref: Ref) -> None:
    if value not in allowed:
        raise VocabularyError(f"{what} {value!r} at {ref.source} {ref.path_text}; allowed: {allowed}")


def grade_ref(r: Ref | None) -> Ref | None:
    if r is not None:
        _check(r.value, ALL_GRADES, "grade", r)
    return r


def outcome_ref(r: Ref | None) -> Ref | None:
    if r is not None:
        _check(r.value, OUTCOMES, "outcome", r)
    return r


# ----------------------------------------------------------------------------------------------- the case


@dataclass
class Stage:
    name: str
    before: Ref | None
    after: Ref


@dataclass
class CandidateCase:
    cid: str
    rank: int
    index: int
    row: Ref | None
    col: Ref | None
    branch: Ref
    score: Ref
    area_px: Ref | None
    shape: dict[str, Ref]
    tests: dict[str, dict[str, Ref | None]]  # name -> outcome, value, limit
    chain: list[Stage]
    final: str
    flags: list[str]
    persist: dict[str, Ref] | None = None
    sam: dict[str, Ref | None] | None = None
    sam_box: Ref | None = None
    votes: list[dict[str, Ref]] | None = None
    vote_note: Ref | None = None
    probe: dict[str, Ref] | None = None
    verdict: dict[str, Ref] | None = None
    checks: list[Ref] = field(default_factory=list)
    not_run: list[Ref] = field(default_factory=list)
    half_rate: Ref | None = None  # plan item 15a, beside the score; never read into a grade or an order
    half_rate_below: Ref | None = None


@dataclass
class Direction:
    key: str
    source: str
    path: tuple
    from_strip: Ref
    to_strip: Ref
    registration: Ref | None
    match_radius_px: Ref | None
    counts: Ref | None
    by_branch: Ref | None
    inject_check: Ref | None


@dataclass
class StripCase:
    strip: str
    valid_area_km2: Ref | None
    scale_m: Ref | None
    tiles: Ref | None
    n_candidates: Ref
    list_stage: str  # which file the full-list grade counts come from
    list_grade_counts: dict[str, Ref]
    shown_grade_counts: dict[str, Ref]
    candidates: list[CandidateCase]
    directions: list[Direction]
    model_files: dict[str, str]  # kind -> source key
    probe_total: dict[str, Ref] | None
    review: dict[str, Any] | None
    manifest_note: str | None


@dataclass
class Case:
    run: Ref | None
    detector: Ref | None
    git_commit: Ref | None
    sources: list[Source]
    strips: list[StripCase]
    ledger: Source | None
    coverage: Source | None
    coverage_figure: Path | None
    score: Source | None
    notes: list[str]


def _grade_of(v: str) -> int:
    return GRADES.index(v) if v in GRADES else len(GRADES)


def _chain(stages: list[Stage]) -> tuple[str, list[str]]:
    """The final grade (the lowest a stage ended at; a stage can only lower) and the inconsistencies."""
    flags: list[str] = []
    prev: Stage | None = None
    for s in stages:
        if s.before is not None and _grade_of(s.after.value) < _grade_of(s.before.value):
            flags.append(f"{s.name}: grade raised from {s.before.value} to {s.after.value} in {s.after.source}")
        if s.before is not None and prev is not None and s.before.value != prev.after.value:
            flags.append(
                f"{s.name}: started from {s.before.value} but {prev.name} ended at {prev.after.value} "
                f"({s.before.source} against {prev.after.source})"
            )
        prev = s
    outs = [s.after.value for s in stages]
    ordered = [g for g in outs if g in GRADES]
    if ordered:
        final = max(ordered, key=_grade_of)
    else:
        final = NOT_ASSESSED
    if outs and final != outs[-1]:
        flags.append(f"final grade {final} is not the last stage's {outs[-1]}")
    return final, flags


def _model_source(models_dir: Path | None, kind: str, sid: str) -> Source | None:
    if models_dir is None:
        return None
    p = Path(models_dir) / f"{kind}_{sid}.json"
    return Source.read(f"{kind}:{sid}", p) if p.exists() else None


def _candidate(
    cands: Source,
    sid: str,
    i: int,
    rank: int,
    pers: tuple[Source, tuple] | None,
    sam: Source | None,
    votes: Source | None,
    probe: Source | None,
    review: Source | None,
) -> CandidateCase:
    base = ("strips", sid, "candidates", i)
    cid = candidate_id(rank)
    chain = [Stage("detector", None, grade_ref(cands.get(*base, "grade")))]
    shape = {k: r for k in SHAPE_FEATURES if (r := cands.get(*base, "extra", k)) is not None}
    tests: dict[str, dict[str, Ref | None]] = {}
    for name in cands.walk(base + ("tests",), {}) or {}:
        tests[name] = {
            "outcome": outcome_ref(cands.get(*base, "tests", name, "outcome")),
            "value": cands.get(*base, "tests", name, "value"),
            "limit": cands.get(*base, "tests", name, "limit"),
        }
    cc = CandidateCase(
        cid,
        rank + 1,
        i,
        cands.get(*base, "row"),
        cands.get(*base, "col"),
        cands.get(*base, "branch"),
        cands.get(*base, "score"),
        cands.get(*base, "area_px"),
        shape,
        tests,
        chain,
        "",
        [],
        half_rate=cands.get(*base, RATE_FIELD),
        half_rate_below=cands.get(*base, BELOW_FIELD),
    )
    if pers is not None:
        src, dpath = pers
        pbase = dpath + ("candidates", i)
        if src.has(*pbase):
            if src.walk(pbase + ("row",), None) != cands.walk(base + ("row",), None):
                raise JoinError(f"{src.key}: candidate {i} is not the candidate {i} of {cands.key}")
            chain.append(Stage("persistence", None, grade_ref(src.get(*pbase, "grade"))))
            p = pbase + ("extra", "persist")
            cc.persist = {
                k: r
                for k in ("seen", "distance_px", "branch_b", "score_b", "note")
                if (r := src.get(*p, k)) is not None
            }
            if "seen" not in cc.persist and src.has(*p, "seen"):  # seen can be None: unregistered
                cc.persist["seen"] = Ref(None, src.key, p + ("seen",))
    if sam is not None and sam.has("records", rank):
        rb = ("records", rank)
        cc.sam_box = sam.get(*rb, "box")
        cc.sam = {"found": sam.get(*rb, "found"), "confidence": sam.get(*rb, "confidence")}
        for k in SAM_MEASUREMENTS:
            cc.sam[k] = sam.get(*rb, "measurements", k)
        for name in sam.walk(rb + ("tests",), {}) or {}:
            tests[name] = {
                "outcome": outcome_ref(sam.get(*rb, "tests", name, "outcome")),
                "value": sam.get(*rb, "tests", name, "value"),
                "limit": sam.get(*rb, "tests", name, "limit"),
            }
        if (nr := sam.get(*rb, "not_run")) is not None:
            cc.not_run.append(nr)
    if votes is not None and votes.has("records", rank):
        rb = ("records", rank)
        if votes.has(*rb, "votes"):
            cc.votes = []
            for k in range(len(votes.walk(rb + ("votes",)))):
                v = votes.get(*rb, "votes", k, "verdict")
                _check(v.value, VOTE_VERDICTS, "vote", v)
                cc.votes.append(
                    {
                        "verdict": v,
                        "confidence": votes.get(*rb, "votes", k, "confidence"),
                        "reason": votes.get(*rb, "votes", k, "reason"),
                        "off_schema": votes.get(*rb, "votes", k, "off_schema"),
                    }
                )
            cc.vote_note = votes.get(*rb, "note")
            chain.append(
                Stage("votes", grade_ref(votes.get(*rb, "grade_before")), grade_ref(votes.get(*rb, "grade_after")))
            )
        if (nr := votes.get(*rb, "not_run")) is not None:
            cc.not_run.append(nr)
    if probe is not None and probe.has("records", rank, "summary"):
        sb = ("records", rank, "summary")
        cc.probe = {
            k: r for k in ("n", "recognised", "max_confidence", "claims") if (r := probe.get(*sb, k)) is not None
        }
    if review is not None and review.has("grades", cid):
        chain.append(
            Stage(
                "review", grade_ref(review.get("grades", cid, "before")), grade_ref(review.get("grades", cid, "after"))
            )
        )
        if review.has("verdicts", cid):
            a = review.get("verdicts", cid, "action")
            _check(a.value, ACTIONS, "action", a)
            cc.verdict = {
                "action": a,
                "cites": review.get("verdicts", cid, "cites"),
                "reason": review.get("verdicts", cid, "reason"),
                "reviewed": review.get("grades", cid, "reviewed"),
            }
        else:
            cc.verdict = {"reviewed": review.get("grades", cid, "reviewed")}
        for k, ch in enumerate(review.walk(("checks",), []) or []):
            if ch.get("id") == cid:
                cc.checks.append(review.get("checks", k))
    cc.final, cc.flags = _chain(chain)
    return cc


def _manifest_note(manifest: Source | None, cands: Source, sid: str, order: list[int]) -> str | None:
    if manifest is None:
        return None
    ids = manifest.walk(("ids",), {}) or {}
    bad = []
    for cid, pos in ids.items():
        rank = int(cid[1:])
        if rank >= len(order):
            bad.append(cid)
            continue
        c = cands.walk(("strips", sid, "candidates", order[rank]))
        if (c.get("row"), c.get("col")) != (pos.get("row"), pos.get("col")):
            bad.append(cid)
    if bad:
        return f"the manifest {manifest.key} disagrees with the rank order for ids {bad}; model records are not joined"
    return None


def _grade_counts(src: Source, path: tuple, grades_of: list[str]) -> dict[str, Ref]:
    out = {}
    for g in ALL_GRADES:
        n = sum(1 for x in grades_of if x == g)
        out[g] = src.count(*path, where=f"grade = {g}", n=n)
    return out


def _strip(
    cands: Source,
    sid: str,
    top: int,
    persist_sources: list[Source],
    models_dir: Path | None,
    notes: list[str],
) -> StripCase:
    clist = cands.walk(("strips", sid, "candidates"), [])
    order = sorted(range(len(clist)), key=lambda i: -clist[i]["score"])
    directions: list[Direction] = []
    pers: tuple[Source, tuple] | None = None
    for ps in persist_sources:
        for dkey, d in (ps.walk(("directions",), {}) or {}).items():
            if d.get("from") != sid:
                continue
            dpath = ("directions", dkey)
            directions.append(
                Direction(
                    dkey,
                    ps.key,
                    dpath,
                    ps.get(*dpath, "from"),
                    ps.get(*dpath, "to"),
                    ps.get(*dpath, "registration"),
                    ps.get(*dpath, "match_radius_px"),
                    ps.get(*dpath, "counts"),
                    ps.get(*dpath, "by_branch"),
                    ps.get(*dpath, "inject_check"),
                )
            )
            if pers is None:
                pers = (ps, dpath)
            else:
                notes.append(
                    f"{sid}: grades after persistence come from {pers[0].key} {fmt_path(pers[1])}; "
                    f"{ps.key} {dkey} is shown but not joined"
                )
    sam = _model_source(models_dir, "sam", sid)
    votes = _model_source(models_dir, "votes", sid)
    probe = _model_source(models_dir, "probe", sid)
    review = _model_source(models_dir, "review", sid)
    manifest = _model_source(models_dir, "manifest", sid)
    mnote = _manifest_note(manifest, cands, sid, order)
    if mnote:
        sam = votes = probe = review = None
    n_model = max(
        [len(s.walk(("records",), []) or []) for s in (sam, votes, probe) if s is not None]
        + [len(review.walk(("grades",), {}) or {}) if review is not None else 0]
    )
    shown = list(range(min(len(order), max(top, n_model))))
    ccs = [_candidate(cands, sid, order[r], r, pers, sam, votes, probe, review) for r in shown]
    if pers is not None:
        list_src, list_path, stage = pers[0], pers[1] + ("candidates",), "persistence"
    else:
        list_src, list_path, stage = cands, ("strips", sid, "candidates"), "detector"
    list_grades = [c.get("grade") for c in list_src.walk(list_path, [])]
    for g in list_grades:
        if g not in ALL_GRADES:
            raise VocabularyError(f"grade {g!r} in {list_src.key} {fmt_path(list_path)}")
    shown_counts = {}
    for g in ALL_GRADES:
        shown_counts[g] = cands.count(
            "strips",
            sid,
            "candidates",
            where=f"final grade = {g}, over the {len(ccs)} shown",
            n=sum(1 for c in ccs if c.final == g),
        )
    probe_total = {"candidates": probe.count("records")} if probe is not None else None
    rev = None
    if review is not None:
        log = review.walk(("tool_log",), []) or []
        tools = sorted({t.get("tool") for t in log})
        grades = review.walk(("grades",), {}) or {}
        rev = {
            "backend_turns": review.get("turns"),
            "stopped": review.get("stopped"),
            "verdicts": review.count("verdicts"),
            "lowered": review.count(
                "grades",
                where="after differs from before",
                n=sum(1 for g in grades.values() if g.get("after") != g.get("before")),
            ),
            "tool_calls": review.count("tool_log"),
            "by_tool": {
                t: review.count("tool_log", where=f"tool = {t}", n=sum(1 for x in log if x.get("tool") == t))
                for t in tools
            },
            "checks": review.count("checks"),
            "unrecorded": review.get("final", "unrecorded"),
        }
    files = {
        k: s.key for k, s in (("sam", sam), ("votes", votes), ("probe", probe), ("review", review)) if s is not None
    }
    return StripCase(
        sid,
        cands.get("strips", sid, "valid_area_km2"),
        cands.get("strips", sid, "scale_m"),
        cands.get("strips", sid, "tiles"),
        cands.count("strips", sid, "candidates"),
        stage,
        _grade_counts(list_src, list_path, list_grades),
        shown_counts,
        ccs,
        directions,
        files,
        probe_total,
        rev,
        mnote,
    )


def load_case(
    candidates: Path,
    models_dir: Path | None = None,
    persist: list[Path] | None = None,
    coverage: Path | None = None,
    score: Path | None = None,
    ledger: Path | None = None,
    top: int = 50,
) -> Case:
    candidates = Path(candidates)
    cands = Source.read("candidates", candidates)
    sources = [cands]
    notes: list[str] = []
    if persist is None:
        persist = sorted(candidates.parent.glob("persist_*.json"))
    persist_sources = [Source.read(f"persist:{p.stem.removeprefix('persist_')}", p) for p in persist]
    sources += persist_sources
    strips = [_strip(cands, sid, top, persist_sources, models_dir, notes) for sid in cands.walk(("strips",), {})]
    seen = {s.key for s in sources}
    for st in strips:
        for kind, key in st.model_files.items():
            if key not in seen:
                sources.append(Source.read(key, Path(models_dir) / f"{kind}_{st.strip}.json"))
                seen.add(key)
    led = None
    lp = Path(ledger) if ledger else (Path(models_dir) / "ledger.json" if models_dir else None)
    if lp is not None and lp.exists():
        led = Source.read("ledger", lp)
        sources.append(led)
    cov = fig = None
    if coverage and Path(coverage).exists():
        cov = Source.read("coverage", Path(coverage))
        sources.append(cov)
        png = Path(coverage).with_suffix(".png")
        fig = png if png.exists() else None
    sc = None
    if score and Path(score).exists():
        sc = Source.read("score", Path(score))
        sources.append(sc)
    return Case(
        cands.get("run"),
        cands.get("detector", "version"),
        cands.get("git_commit"),
        sources,
        strips,
        led,
        cov,
        fig,
        sc,
        notes,
    )
