"""The model passes over a candidate list, written against a pixel reader so the tests run on arrays.

``read(row, col, size)`` returns ``(data, valid)`` for a square window centred on a candidate; the
scripts bind it to ``Strip.read_centered``, the tests to a synthetic array. Candidate ids are ``c000``,
``c001``, ... by rank in the list given; the mapping from id to pixel position stays in the run's manifest
under ``out/`` and never enters a prompt.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from landers.detect import DetectorConfig
from landers.models import crops, sam, wonder
from landers.models.backend import ModelClient, make_backend
from landers.models.ledger import CapError, Ledger, register_run, spent_usd
from landers.models.spark import EvidenceStore, evidence_record

Reader = Callable[[float, float, int], tuple[np.ndarray, np.ndarray]]


def candidate_id(i: int) -> str:
    return f"c{i:03d}"


def open_client(kind: str, out_dir: Path, ledger_name: str = "ledger.json", item: str = "") -> ModelClient:
    """A client on backend ``kind`` with the ledger continued from ``out_dir/ledger.json``. A real run's ledger goes on the
    register before anything is sent (``item`` names it there), and the cumulative dollar cap counts every other ledger on
    the register."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    directory = {"dry-run": out_dir / "model_requests", "recorded": out_dir / "model_recordings"}.get(kind)
    if kind == "real":
        directory = out_dir / "model_recordings"
    backend = make_backend(kind, directory)
    ledger = Ledger.load(out_dir / ledger_name)
    if kind == "real":
        register_run(ledger.path, item or out_dir.name)
    ledger.prior_usd = spent_usd(exclude=ledger.path)
    return ModelClient(backend, ledger)


def top_candidates(cands: list[dict], n: int) -> list[dict]:
    return sorted(cands, key=lambda c: -c["score"])[:n]


def array_reader(data: np.ndarray, valid: np.ndarray | None = None) -> Reader:
    valid = np.ones(data.shape, bool) if valid is None else valid

    def read(row: float, col: float, size: int):
        return crops.square_crop(data, valid, row, col, size)

    return read


@dataclass
class SamPassConfig:
    size: int = 256
    pad: float = 1.0
    limits: sam.SamLimits = None
    detector: DetectorConfig = None

    def __post_init__(self):
        self.limits = self.limits or sam.SamLimits()
        self.detector = self.detector or DetectorConfig()


def sam_pass(
    client: ModelClient, read: Reader, cands: list[dict], scale_m: float, cfg: SamPassConfig | None = None
) -> list[dict]:
    """One SAM request per candidate: a box from the detector's blob in a crop around it; measurements and
    the size and shape tests from the mask. Stops at the ledger cap and records the rest as not run."""
    cfg = cfg or SamPassConfig()
    out = []
    for i, c in enumerate(cands):
        data, valid = read(c["row"], c["col"], cfg.size)
        png = crops.to_png(crops.stretch(data, valid, 0.5, 99.5))
        box = sam.box_for_blob(cfg.size // 2, cfg.size // 2, c["area_px"], cfg.size, cfg.pad)
        rec: dict = {"id": candidate_id(i), "branch": c["branch"], "box": box.to_json()}
        try:
            result = client.sam(sam.sam_request(png, cfg.size, [box]))
        except CapError as e:
            rec.update({"found": None, "confidence": 0.0, "measurements": {"area_px": 0}, "not_run": str(e)})
            rec["tests"] = sam.size_shape_tests(rec["measurements"], c["branch"], cfg.detector, cfg.limits, 0.0)
            out.append(rec)
            continue
        m = sam.measure_result(result, [box], scale_m, data)[0]
        rec.update(m)
        rec["tests"] = sam.size_shape_tests(m["measurements"], c["branch"], cfg.detector, cfg.limits, m["confidence"])
        out.append(rec)
    return out


def vote_pass(
    client: ModelClient,
    read: Reader,
    cands: list[dict],
    reference: Reader | None = None,
    reference_at: tuple[float, float] | None = None,
    n_votes: int = 3,
    size: int = 256,
    seed: int = 0,
    probe: bool = False,
    rule: wonder.VoteRule | None = None,
    examples: Callable[[int, int, crops.Augmentation], list[tuple[str, bytes]]] | None = None,
    only: set[int] | None = None,
    on_record: Callable[[dict], None] | None = None,
    saturated_bright: bool = False,
) -> list[dict]:
    """Three augmented blind crops per candidate; votes (or the recognition probe) on each. With votes, the
    grade after ``apply_votes`` is recorded beside the grade before; nothing goes up.

    ``examples(i, j, aug)`` gives the labelled example views for vote ``j`` of candidate ``i`` (the few-shot
    prompt, plan item 9d; None keeps the plain prompt). ``only`` votes on those ranks alone and still draws
    every rank's augmentations, so a vote on rank i is the same request whichever ranks run with it.
    ``on_record`` is called with each record as it is made, so a long pass can be written as it lands."""
    rng = np.random.default_rng(seed)
    out = []
    for i, c in enumerate(cands):
        augs = crops.draw_augmentations(rng, n_votes, size)
        if only is not None and i not in only:
            continue
        data, valid = read(c["row"], c["col"], size + size // 2)
        ref = None
        if reference is not None and reference_at is not None:
            rdata, rvalid = reference(reference_at[0], reference_at[1], size + size // 2)
            ref = (rdata, rvalid, rdata.shape[0] / 2.0, rdata.shape[1] / 2.0)
        views = [
            crops.build_crop(data, valid, data.shape[0] / 2.0, data.shape[1] / 2.0, size, 4, a, ref, saturated_bright)
            for a in augs
        ]
        if examples is not None:
            for j, (v, a) in enumerate(zip(views, augs)):
                v.examples = examples(i, j, a)
        rec: dict = {"id": candidate_id(i), "branch": c["branch"], "crops": [v.to_json() for v in views]}
        rec["prompt"] = wonder.FEWSHOT_VERSION if examples is not None else wonder.PLAIN_VERSION
        try:
            if probe:
                rec["probe"] = wonder.probe(client, views)
                rec["summary"] = wonder.probe_summary(rec["probe"])
            else:
                rec["votes"] = wonder.cast_votes(client, views)
                rec["grade_before"] = c["grade"]
                rec["grade_after"], rec["note"] = wonder.apply_votes(c["grade"], rec["votes"], rule)
        except CapError as e:
            rec["not_run"] = str(e)
        out.append(rec)
        if on_record is not None:
            on_record(rec)
    return out


def single_vote(
    client: ModelClient,
    read: Reader,
    cand: dict,
    index: int,
    reference: tuple[np.ndarray, np.ndarray, float, float] | None = None,
    rule: wonder.SingleVoteRule | None = None,
    size: int = 256,
    seed: int = 0,
) -> dict:
    """One vote on the plain view; two more on augmented views when the first falls in the rule's borderline band. The
    augmentations hang on the seed and the rank alone, so a rank's requests do not depend on what ran before it. Saturated
    pixels are drawn bright. A CapError goes to the caller."""
    rule = rule or wonder.SingleVoteRule()
    augs = crops.draw_augmentations(np.random.default_rng([seed, index]), 3, size)
    data, valid = read(cand["row"], cand["col"], size + size // 4)
    views = [
        crops.build_crop(data, valid, data.shape[0] / 2.0, data.shape[1] / 2.0, size, 4, a, reference, True) for a in augs
    ]
    votes = wonder.cast_votes(client, views[:1])
    if rule.borderline(votes[0]):
        votes += wonder.cast_votes(client, views[1:])
    grade, note = rule.apply(cand["grade"], votes)
    return {
        "id": candidate_id(index),
        "branch": cand["branch"],
        "crops": [v.to_json() for v in views[: len(votes)]],
        "prompt": wonder.PLAIN_VERSION,
        "crop_draw": "saturated-bright",
        "rule": rule.version,
        "votes": votes,
        "grade_before": cand["grade"],
        "grade_after": grade,
        "note": note,
    }


def build_store(
    cands: list[dict],
    thresholds: dict,
    strip_key: str = "strip_a",
    sam_records: list[dict] | None = None,
    vote_records: list[dict] | None = None,
    checks=None,
) -> EvidenceStore:
    sam_by = {r["id"]: r for r in sam_records or []}
    votes_by = {r["id"]: r.get("votes") for r in vote_records or []}
    records = {}
    for i, c in enumerate(cands):
        cid = candidate_id(i)
        c = dict(c)
        if cid in votes_by and votes_by[cid] is not None:
            vr = next(r for r in vote_records if r["id"] == cid)
            c["grade"] = vr.get("grade_after", c["grade"])
        records[cid] = evidence_record(c, cid, sam_by.get(cid), votes_by.get(cid))
    return EvidenceStore(records, {strip_key: list(records)}, thresholds, checks)


def check_runner(
    client: ModelClient,
    read: Reader,
    cands: list[dict],
    scale_m: float,
    seed: int = 1,
    persist: dict | None = None,
    saturated_bright: bool = False,
):
    """The bounded checks Spark may order. ``zoom_pass``: SAM on a 512 px crop. ``more_votes``: three more
    votes with a new seed. ``second_date_check``: the persistence record when the run has one. Each is
    bounded by the ledger through the client; a CapError comes back to the reviewer as a refusal."""
    by_id = {candidate_id(i): (i, c) for i, c in enumerate(cands)}

    def run(cid: str, kind: str) -> dict:
        i, c = by_id[cid]
        if kind == "zoom_pass":
            rec = sam_pass(client, read, [c], scale_m, SamPassConfig(size=512, pad=1.5))[0]
            if rec.get("not_run"):
                raise CapError(rec["not_run"])
            return {
                "found": rec["found"],
                "confidence": rec["confidence"],
                **rec["measurements"],
                "tests": rec["tests"],
            }
        if kind == "more_votes":
            rec = vote_pass(client, read, [c], n_votes=3, seed=seed + 1000 + i, saturated_bright=saturated_bright)[0]
            if rec.get("not_run"):
                raise CapError(rec["not_run"])
            return {"votes": rec["votes"], "grade_after": rec["grade_after"], "note": rec["note"]}
        if kind == "second_date_check":
            p = (c.get("extra") or {}).get("persist") if persist is None else persist.get(cid)
            if p is None:
                return {"available": False, "note": "no second date in this run"}
            return {"available": True, "seen": p.get("seen"), "note": p.get("note", "")}
        raise ValueError(kind)

    return run


def write_json(path: Path, obj) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n")
    return path
