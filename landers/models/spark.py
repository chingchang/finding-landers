"""Muse Spark, the reviewer: structured evidence in, cited verdicts out, keep or lower only.

Spark never sees pixels. Its five tools read the evidence store and nothing else:

- ``list_candidates(strip_key)``: ids, grades, test outcomes, persistence, SAM measurements, votes.
- ``get_candidate(id)``: the full evidence record.
- ``read_thresholds()``: ``controls/thresholds.json`` as is.
- ``request_check(id, kind)``: one of ``zoom_pass``, ``second_date_check``, ``more_votes``; bounded by the
  ledger through the runner the caller supplies; the result comes back as evidence.
- ``record_verdict(id, action, cites, reason)``: ``keep`` or ``lower``, never raise; ``cites`` names
  evidence fields that exist; every number in ``reason`` must be a number in the record. A verdict that
  fails any of this is rejected and the tool says why.

The evidence record is built by ``evidence_record`` from a whitelist of fields: no row, column, observation
id, coordinate or date is ever in it, and the store refuses a record the leak guard rejects. Strip keys
are neutral names (``strip_a``) whose meaning lives outside the prompt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from landers.models import leak
from landers.models.backend import ModelClient, SparkRequest, SparkTurn
from landers.models.wonder import GRADES

ACTIONS = ("keep", "lower")
CHECK_KINDS = ("zoom_pass", "second_date_check", "more_votes")
MAX_TURNS = 12
THRESHOLD_PROVENANCE = ("decided_by", "decided_on")

SYSTEM_PROMPT = (
    "You are the reviewer in a search of orbital imagery for lost spacecraft hardware. You never see pixels. "
    "You read structured evidence through tools: for each candidate, the detector branch and score, the "
    "physical test outcomes (pass, fail, unsure, not run), persistence across two dates, mask measurements "
    "from a segmentation model, and advisory votes from a vision model. Grades are: candidate, needs second "
    "look, likely natural, not assessed. You may keep a grade or lower it; you can never raise one, and no "
    "model opinion raises one. For every candidate you review, call record_verdict with the action, the "
    "evidence fields your reason rests on, and a one-sentence reason. Every number in a reason must be "
    "copied from the evidence record; do not compute, round or estimate. When a bounded check would decide "
    "a case, call request_check first and read the result. Finish with the final JSON listing the verdicts "
    "you recorded. Use only the vocabulary above; never use found, discovered, confirmed or proven."
)

# Plan item 14: 9c's reviews spent their turns on fetches and checks, and two recorded no verdict at all.
ONE_TURN_CLAUSE = (
    " Work in this order: read the candidates and the thresholds; order any checks; then, in one single turn, call "
    "record_verdict once for every candidate, all together; then give the final JSON. Do not fetch again after you "
    "start recording."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_candidates",
            "description": "Candidates of one strip key: grade, test outcomes, persistence, mask measurements, votes.",
            "parameters": {
                "type": "object",
                "properties": {"strip_key": {"type": "string"}},
                "required": ["strip_key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_candidate",
            "description": "The full evidence record of one candidate.",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_thresholds",
            "description": "The adopted thresholds file, as is.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_check",
            "description": "Order one bounded check on a candidate: zoom_pass, second_date_check or more_votes. "
            "Refused when the ledger cap would be passed. The result is added to the evidence.",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "kind": {"type": "string", "enum": list(CHECK_KINDS)}},
                "required": ["id", "kind"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_verdict",
            "description": "Record keep or lower for a candidate, citing evidence fields. Rejected when it "
            "cites nothing, cites a field that does not exist, or uses a number not in the record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "cites": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "reason": {"type": "string", "maxLength": 400},
                },
                "required": ["id", "action", "cites", "reason"],
                "additionalProperties": False,
            },
        },
    },
]

FINAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "action", "cites"],
                "properties": {
                    "id": {"type": "string"},
                    "action": {"type": "string", "enum": list(ACTIONS)},
                    "cites": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}
FINAL_FORMAT = {"type": "json_schema", "json_schema": {"name": "review", "strict": True, "schema": FINAL_SCHEMA}}

# Fields of a detector candidate that may reach the reviewer. Position and provenance never do.
EXTRA_WHITELIST = (
    "circularity",
    "fill",
    "elongation",
    "edge_sharpness",
    "tile_rank",
    "shadow_alignment",
    "shadow_len_px",
    "height_m",
    "raw_score",
)


def evidence_record(cand: dict, candidate_id: str, sam: dict | None = None, votes: list[dict] | None = None) -> dict:
    """The blind evidence record of one detector candidate (a ``Candidate.to_json`` dict, possibly with
    ``extra.persist`` from the persistence step)."""
    extra = cand.get("extra", {}) or {}
    rec: dict = {
        "id": candidate_id,
        "branch": cand["branch"],
        "grade": cand["grade"],
        "score": cand["score"],
        "area_px": cand.get("area_px"),
        "shape": {k: extra[k] for k in EXTRA_WHITELIST if k in extra},
        "tests": dict(cand.get("tests", {})),
    }
    p = extra.get("persist")
    if p is not None:
        rec["persistence"] = {"seen": p.get("seen"), "note": p.get("note", "")}
    else:
        rec["persistence"] = {"seen": None, "note": "one date only"}
    if sam is not None:
        rec["sam"] = {"found": sam.get("found"), "confidence": sam.get("confidence"), **sam.get("measurements", {})}
        rec["tests"].update(sam.get("tests", {}))
    if votes is not None:
        rec["votes"] = [{"verdict": v["verdict"], "confidence": v["confidence"], "reason": v["reason"]} for v in votes]
    leak.check_strings(rec, f"evidence {candidate_id}")
    return rec


def _paths(obj, prefix: str = "") -> set[str]:
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.add(p)
            out |= _paths(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{prefix}[{i}]"
            out.add(p)
            out |= _paths(v, p)
    return out


def _numbers(obj) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int | float):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= _numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _numbers(v)
    return out


NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")


def numbers_not_in_record(reason: str, record: dict) -> list[str]:
    """Numeric tokens of ``reason`` that are not a value in the record (exact, or the value rounded to
    the token's decimals)."""
    have = _numbers(record)
    bad = []
    for tok in NUMBER.findall(reason):
        x = float(tok)
        dec = len(tok.split(".")[1]) if "." in tok else 0
        if not any(x == v or round(v, dec) == x for v in have):
            bad.append(tok)
    return bad


@dataclass
class EvidenceStore:
    """What the reviewer can read. ``checks`` runs a bounded check and returns a dict of new evidence; it
    is given by the caller and is where the ledger bounds the follow-ups."""

    records: dict[str, dict]
    strips: dict[str, list[str]]  # strip key -> candidate ids
    thresholds: dict
    checks: Callable[[str, str], dict] | None = None
    verdicts: dict[str, dict] = field(default_factory=dict)
    check_log: list[dict] = field(default_factory=list)

    def list_candidates(self, strip_key: str) -> dict:
        ids = self.strips.get(strip_key)
        if ids is None:
            return {"error": f"unknown strip key; known: {sorted(self.strips)}"}
        return {"strip_key": strip_key, "candidates": [self.records[i] for i in ids]}

    def get_candidate(self, id: str) -> dict:
        return self.records.get(id) or {"error": f"unknown candidate id {id}"}

    def read_thresholds(self) -> dict:
        """The thresholds without their provenance: who decided them and when is a date and a name, which
        the leak guard refuses in a prompt (the first dry run on a real strip stopped on ``decided_on``)."""
        return {k: v for k, v in self.thresholds.items() if k not in THRESHOLD_PROVENANCE}

    def request_check(self, id: str, kind: str) -> dict:
        if id not in self.records:
            return {"error": f"unknown candidate id {id}"}
        if kind not in CHECK_KINDS:
            return {"error": f"unknown check kind; one of {list(CHECK_KINDS)}"}
        if self.checks is None:
            return {"refused": "no checks are available in this run"}
        try:
            result = self.checks(id, kind)
        except Exception as e:  # a CapError or a missing strip: the reviewer is told, the run goes on
            self.check_log.append({"id": id, "kind": kind, "refused": str(e)})
            return {"refused": str(e)}
        leak.check_strings(result, f"check {kind} {id}")
        self.records[id].setdefault("checks", {})[kind] = result
        self.check_log.append({"id": id, "kind": kind, "result": result})
        return {"id": id, "kind": kind, "result": result}

    def record_verdict(self, id: str, action: str, cites: list, reason: str) -> dict:
        rec = self.records.get(id)
        if rec is None:
            return {"rejected": f"unknown candidate id {id}"}
        if action not in ACTIONS:
            return {"rejected": f"action must be keep or lower, not {action!r}; a grade is never raised"}
        if not cites:
            return {"rejected": "a verdict must cite at least one evidence field"}
        known = _paths(rec)
        missing = [c for c in cites if c not in known]
        if missing:
            return {"rejected": f"cited fields not in the record: {missing}", "fields": sorted(known)[:60]}
        bad = numbers_not_in_record(reason, rec)
        if bad:
            return {"rejected": f"numbers not copied from the evidence: {bad}"}
        for w in ("discovered", "confirmed", "proven"):  # "found" is an evidence field name (sam.found)
            if re.search(rf"\b{w}\b", reason, re.I):
                return {"rejected": f"the word {w!r} is not in the vocabulary"}
        self.verdicts[id] = {"action": action, "cites": list(cites), "reason": reason}
        return {"recorded": True, "id": id, "action": action}

    def dispatch(self, name: str, args: dict) -> dict:
        fn = {
            "list_candidates": self.list_candidates,
            "get_candidate": self.get_candidate,
            "read_thresholds": self.read_thresholds,
            "request_check": self.request_check,
            "record_verdict": self.record_verdict,
        }.get(name)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}


def apply_verdicts(records: dict[str, dict], verdicts: dict[str, dict]) -> dict[str, dict]:
    """Grades after review: ``lower`` moves one step down GRADES; ``keep`` and anything unreviewed stay."""
    out = {}
    for cid, rec in records.items():
        g = rec["grade"]
        v = verdicts.get(cid)
        new = g
        if v and v["action"] == "lower" and g in GRADES and GRADES.index(g) + 1 < len(GRADES):
            new = GRADES[GRADES.index(g) + 1]
        out[cid] = {"before": g, "after": new, "reviewed": v is not None}
    return out


@dataclass
class ReviewResult:
    strip_key: str
    turns: int
    verdicts: dict
    grades: dict
    final: dict | None
    tool_log: list[dict]
    reasoning: list[str]
    stopped: str

    def to_json(self) -> dict:
        return {
            "strip_key": self.strip_key,
            "turns": self.turns,
            "stopped": self.stopped,
            "verdicts": self.verdicts,
            "grades": self.grades,
            "final": self.final,
            "tool_log": self.tool_log,
        }


def review(
    client: ModelClient, store: EvidenceStore, strip_key: str, max_turns: int = MAX_TURNS, one_turn: bool = False
) -> ReviewResult:
    """The standard tool loop (docs/models.md): replay the assistant message, then one tool message per
    call, until a reply has no tool calls or the turn cap is hit. ``one_turn`` asks for every verdict in one turn after
    the fetches and, with two turns left, names the candidates still without one."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + (ONE_TURN_CLAUSE if one_turn else "")},
        {"role": "user", "content": f"Review the candidates for strip key: {strip_key}. Record a verdict for each."},
    ]
    tool_log: list[dict] = []
    reasoning: list[str] = []
    final = None
    stopped = "turn cap"
    turns = 0
    for turn in range(1, max_turns + 1):
        turns = turn
        if one_turn and turn == max_turns - 1:
            missing = [c for c in store.strips.get(strip_key, []) if c not in store.verdicts]
            if missing:
                nudge = f"Two turns remain. Record your verdicts now for: {', '.join(missing)}."
                messages.append({"role": "user", "content": nudge})
        reply = client.spark(SparkRequest(messages, TOOLS, FINAL_FORMAT))
        if reply.reasoning:
            reasoning.append(reply.reasoning)
        if not reply.tool_calls:
            final = _parse_final(reply.content)
            stopped = "final answer" if final is not None else "no tool calls and no parsable final answer"
            break
        messages.append(reply.as_message())
        for tc in reply.tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError as e:
                args, result = {}, {"error": f"arguments are not JSON: {e}"}
            else:
                result = store.dispatch(name, args)
            tool_log.append({"turn": turn, "tool": name, "args": args, "result": _summary(result)})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result)})
    if final is not None:
        final["unrecorded"] = [v["id"] for v in final.get("verdicts", []) if v["id"] not in store.verdicts]
    return ReviewResult(
        strip_key,
        turns,
        dict(store.verdicts),
        apply_verdicts(store.records, store.verdicts),
        final,
        tool_log,
        reasoning,
        stopped,
    )


def _parse_final(content: str | None) -> dict | None:
    if not content:
        return None
    try:
        d = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("verdicts"), list):
        return None
    return d


def _summary(result: dict) -> dict:
    s = json.dumps(result)
    return result if len(s) <= 400 else {"keys": sorted(result)[:20], "bytes": len(s)}


# ----------------------------------------------------------------------------------------------- fake Spark


def scripted_turn(req: SparkRequest, script=None) -> SparkTurn:
    """The fake reviewer: list the strip's candidates, fetch each, read the thresholds, then record a
    ``keep`` for every candidate citing its grade and branch, then the final answer. Deterministic; it
    exercises the loop, the tools and the validation without an opinion of its own."""
    msgs = req.messages
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    user = next((m["content"] for m in msgs if m["role"] == "user"), "")
    m = re.search(r"strip key: (\S+?)\.", user)
    strip_key = m.group(1) if m else "strip_a"
    step = len([m for m in msgs if m["role"] == "assistant"])

    def call(i: int, name: str, args: dict) -> dict:
        return {"id": f"fake_{step}_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

    if step == 0:
        return SparkTurn(None, [call(0, "list_candidates", {"strip_key": strip_key})], "fake: list first")
    listing = json.loads(tool_msgs[0]["content"]) if tool_msgs else {}
    ids = [c["id"] for c in listing.get("candidates", [])]
    if step == 1:
        calls = [call(i, "get_candidate", {"id": cid}) for i, cid in enumerate(ids)]
        calls.append(call(len(ids), "read_thresholds", {}))
        return SparkTurn(None, calls, "fake: fetch all records and the thresholds")
    if step == 2:
        calls = []
        for i, cid in enumerate(ids):
            rec = next(c for c in listing["candidates"] if c["id"] == cid)
            reason = f"fake review: grade {rec['grade']} from branch {rec['branch']} with score {rec['score']}; kept"
            calls.append(
                call(
                    i,
                    "record_verdict",
                    {"id": cid, "action": "keep", "cites": ["grade", "branch", "score"], "reason": reason},
                )
            )
        return SparkTurn(None, calls, "fake: keep every candidate")
    final = {"verdicts": [{"id": cid, "action": "keep", "cites": ["grade", "branch", "score"]} for cid in ids]}
    return SparkTurn(json.dumps(final), [], "fake: done")
