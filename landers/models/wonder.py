"""Muse Wonder: advisory votes on blind crops, and the recognition probe.

A vote is recorded and shown. It can lower a grade, never raise one: a candidate stays a candidate on the
physical tests alone, and ``apply_votes`` lowers it one step only when the votes agree it is natural with
confidence. The recognition probe runs first and separately with the same crops and the question "do you
recognise this place or what it shows"; its answer goes on the board, and a yes on a famous site is reported
so the advisory votes are read in that light.

The fixed part of every question comes first so the API's prefix cache can hold it. No question or schema
names a place, a mission or a date; the leak guard checks each one again before it is sent.
"""

from __future__ import annotations

from dataclasses import dataclass

from landers.models.backend import ModelClient, WonderRequest
from landers.models.crops import BlindCrop

GRADES = ("candidate", "needs second look", "likely natural")  # best to worst; "not assessed" is apart
VERDICTS = ("hardware", "natural", "unsure")

VOTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "confidence", "reason"],
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "maxLength": 300},
    },
}

PROBE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recognised", "place", "shows", "confidence"],
    "properties": {
        "recognised": {"type": "boolean"},
        "place": {"type": "string", "maxLength": 200},
        "shows": {"type": "string", "maxLength": 200},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

VOTE_QUESTION = (
    "You are looking at orbital images of planetary ground at about 25 to 50 cm per pixel. "
    "Image 1 is a square at native resolution centred on an object a detector flagged. "
    "Image 2 is the centre of image 1 enlarged 4 times. "
    "{reference_clause}"
    "Question: is the object at the centre of image 1 more consistent with a piece of manufactured hardware "
    "(a metal or fabric object with a crisp outline, a shadow of a raised body, unlike its surroundings) "
    "or with a natural feature (a rock, a crater rim, a slope, a ripple crest, a frost or dust pattern)? "
    "Answer with the schema: verdict hardware, natural or unsure; confidence 0 to 1; reason, one sentence "
    "naming what in the pixels decided it. Say unsure when the pixels do not decide it."
)
REFERENCE_CLAUSE = (
    "Image 3 is a reference: similar ground from elsewhere, with no flagged object, stretched the same way. "
)

PROBE_QUESTION = (
    "You are looking at orbital images of planetary ground. Image 1 is a square at native resolution; "
    "image 2 is its centre enlarged 4 times. "
    "{reference_clause}"
    "Question: do you recognise this place, or what it shows? If you believe you know the location, the "
    "mission or the object, say so in the place and shows fields and set recognised true with your "
    "confidence. If not, set recognised false and describe only what the pixels show."
)


@dataclass
class VoteRule:
    """When votes may lower a grade: at least ``min_natural`` votes of ``natural`` at or above
    ``min_confidence``, and no ``hardware`` vote at or above it. One step down, never two, never up."""

    min_natural: int = 2
    min_confidence: float = 0.7


def vote_request(crop: BlindCrop, effort: str = "low") -> WonderRequest:
    clause = REFERENCE_CLAUSE if crop.reference_png is not None else ""
    return WonderRequest(VOTE_QUESTION.format(reference_clause=clause), crop.images(), VOTE_SCHEMA, "vote", effort)


def probe_request(crop: BlindCrop, effort: str = "low") -> WonderRequest:
    clause = REFERENCE_CLAUSE if crop.reference_png is not None else ""
    return WonderRequest(PROBE_QUESTION.format(reference_clause=clause), crop.images(), PROBE_SCHEMA, "probe", effort)


def parse_vote(data: dict) -> dict:
    """A vote record from the model's JSON; anything off-schema becomes ``unsure`` and is marked."""
    v = data.get("verdict")
    conf = data.get("confidence")
    ok = v in VERDICTS and isinstance(conf, int | float) and 0 <= conf <= 1
    return {
        "verdict": v if ok else "unsure",
        "confidence": float(conf) if ok else 0.0,
        "reason": str(data.get("reason", ""))[:300],
        "off_schema": not ok,
    }


def cast_votes(client: ModelClient, crops: list[BlindCrop]) -> list[dict]:
    """One vote per crop (three augmentations give three votes). Each record keeps its augmentation."""
    votes = []
    for crop in crops:
        r = client.wonder(vote_request(crop))
        rec = parse_vote(r.data)
        rec["augmentation"] = crop.augmentation.to_json()
        rec["tokens"] = {"input": r.input_tokens, "output": r.output_tokens}
        votes.append(rec)
    return votes


def probe(client: ModelClient, crops: list[BlindCrop]) -> list[dict]:
    out = []
    for crop in crops:
        r = client.wonder(probe_request(crop))
        d = r.data
        out.append(
            {
                "recognised": bool(d.get("recognised", False)),
                "place": str(d.get("place", ""))[:200],
                "shows": str(d.get("shows", ""))[:200],
                "confidence": float(d.get("confidence", 0.0) or 0.0),
                "augmentation": crop.augmentation.to_json(),
            }
        )
    return out


def probe_summary(results: list[dict]) -> dict:
    hits = [r for r in results if r["recognised"]]
    return {
        "n": len(results),
        "recognised": len(hits),
        "max_confidence": max((r["confidence"] for r in hits), default=0.0),
        "claims": sorted({r["place"] for r in hits if r["place"]}),
    }


def apply_votes(grade: str, votes: list[dict], rule: VoteRule | None = None) -> tuple[str, str]:
    """The grade after the votes: the same or one step lower. Returns (grade, note)."""
    rule = rule or VoteRule()
    if grade not in GRADES:
        return grade, "not assessed: votes recorded only"
    natural = sum(1 for v in votes if v["verdict"] == "natural" and v["confidence"] >= rule.min_confidence)
    hardware = sum(1 for v in votes if v["verdict"] == "hardware" and v["confidence"] >= rule.min_confidence)
    if natural >= rule.min_natural and hardware == 0:
        i = GRADES.index(grade)
        if i + 1 < len(GRADES):
            return GRADES[
                i + 1
            ], f"lowered by votes: {natural} natural at or above {rule.min_confidence}, none hardware"
        return grade, "already the lowest grade"
    return grade, f"kept: {natural} natural, {hardware} hardware at or above {rule.min_confidence}"
