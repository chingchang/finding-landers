"""One interface for SAM 3.1, Muse Wonder and Muse Spark, and the backends behind it.

Requests are plain dataclasses that know their wire form (``to_wire``), so the dry-run backend can write
exactly what would be sent and the recorded backend can key a saved result by the request's hash. The
``ModelClient`` is the only way to call a backend: it runs the leak guard on every text and image, charges
the ledger before the call, retries transient failures at most three times (each attempt counted), and
records the outcome.

Backends:

- ``FakeBackend``: deterministic, in-process. SAM returns a disc mask inside each box at confidence 0.9;
  Wonder answers a schema with a fixed, non-committal record; Spark runs a scripted review.
- ``RecordedBackend``: replays a saved result by request hash from a directory; with an inner backend it
  records what it does not have. All real responses are kept this way once there are any.
- ``DryRunBackend``: writes the wire request (images replaced by their hash and size) under
  ``out/model_requests/`` and answers from an inner backend (the fake by default).
- ``RealBackend``: the ``openai`` SDK against the Meta Model API. Constructed only by ``make_backend("real")``
  with ``MODEL_API_KEY`` and ``LANDERS_REAL_CALLS=1`` in the environment; imports the SDK lazily so the
  tests need neither the package nor the network.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from landers.models import leak
from landers.models.ledger import Ledger

SAM_MODEL = "sam-3.1"
WONDER_MODEL = "muse-wonder-1.0"
SPARK_MODEL = "muse-spark-1.3"
BASE_URL = "https://api.meta.ai/v1"
MAX_ATTEMPTS = 3


class TransientError(RuntimeError):
    """A 429 or 5xx: the client may retry, counting the attempt."""


class RequestError(RuntimeError):
    """A 400: the request shape is wrong. Never retried."""


class MissingRecording(KeyError):
    """The recorded backend has no result for this request."""


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def image_digest(png: bytes) -> dict:
    return {"sha256": hashlib.sha256(png).hexdigest(), "bytes": len(png)}


# ----------------------------------------------------------------------------------------------- requests


@dataclass(frozen=True)
class Box:
    """Pixel box in the image sent, ``x2`` and ``y2`` inclusive."""

    x1: int
    y1: int
    x2: int
    y2: int

    def to_json(self) -> dict:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}


@dataclass
class SamRequest:
    image_png: bytes
    width: int
    height: int
    boxes: list[Box]
    text: str | None = None  # a noun phrase instead of boxes; the two are never mixed

    def prompt_text(self) -> str:
        from landers.models.sam import build_object_prompt

        if self.text is not None:
            if self.boxes:
                raise ValueError("a SAM request takes boxes or a noun phrase, not both")
            return self.text
        return build_object_prompt(self.width, self.height, self.boxes)

    def to_wire(self, images: str = "data") -> dict:
        img = data_url(self.image_png) if images == "data" else image_digest(self.image_png)
        return {
            "model": SAM_MODEL,
            "stream": True,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": self.prompt_text()},
                        {"type": "input_image", "image_url": img},
                    ],
                }
            ],
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        }

    def texts(self) -> list[str]:
        return [self.prompt_text()]

    def images(self) -> list[bytes]:
        return [self.image_png]


@dataclass
class SamObject:
    object_id: int
    box: Box
    confidence: float
    mask: np.ndarray  # bool, (height, width) of the image sent

    def to_json(self) -> dict:
        return {
            "object_id": self.object_id,
            "box": self.box.to_json(),
            "confidence": round(self.confidence, 3),
            "mask": mask_to_json(self.mask),
        }

    @classmethod
    def from_json(cls, d: dict) -> SamObject:
        return cls(d["object_id"], Box(**d["box"]), d["confidence"], mask_from_json(d["mask"]))


@dataclass
class SamResult:
    objects: list[SamObject]
    raw_text: str = ""

    def to_json(self) -> dict:
        return {"objects": [o.to_json() for o in self.objects], "raw_text": self.raw_text}

    @classmethod
    def from_json(cls, d: dict) -> SamResult:
        return cls([SamObject.from_json(o) for o in d["objects"]], d.get("raw_text", ""))


def mask_to_json(mask: np.ndarray) -> dict:
    m = np.asarray(mask, bool)
    return {"shape": list(m.shape), "bits": base64.b64encode(np.packbits(m.ravel())).decode("ascii")}


def mask_from_json(d: dict) -> np.ndarray:
    h, w = d["shape"]
    bits = np.unpackbits(np.frombuffer(base64.b64decode(d["bits"]), np.uint8))[: h * w]
    return bits.reshape(h, w).astype(bool)


@dataclass
class WonderRequest:
    question: str
    images: list[bytes]
    schema: dict
    schema_name: str = "vote"
    effort: str = "low"

    def to_wire(self, images: str = "data") -> dict:
        parts: list[dict] = [{"type": "text", "text": self.question}]
        for png in self.images:
            url = data_url(png) if images == "data" else image_digest(png)
            parts.append({"type": "image_url", "image_url": {"url": url}})
        return {
            "model": WONDER_MODEL,
            "reasoning_effort": self.effort,
            "messages": [{"role": "user", "content": parts}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": self.schema_name, "strict": True, "schema": self.schema},
            },
        }

    def texts(self) -> list[str]:
        return [self.question, json.dumps(self.schema)]

    def image_list(self) -> list[bytes]:
        return list(self.images)


@dataclass
class WonderResult:
    data: dict
    raw: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    def to_json(self) -> dict:
        return {
            "data": self.data,
            "raw": self.raw,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @classmethod
    def from_json(cls, d: dict) -> WonderResult:
        return cls(d["data"], d.get("raw", ""), d.get("input_tokens", 0), d.get("output_tokens", 0))


@dataclass
class SparkRequest:
    messages: list[dict]
    tools: list[dict]
    response_format: dict | None = None
    effort: str = "medium"

    def to_wire(self, images: str = "data") -> dict:
        body: dict = {
            "model": SPARK_MODEL,
            "reasoning_effort": self.effort,
            "messages": self.messages,
            "tools": self.tools,
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        if self.response_format is not None:
            body["response_format"] = self.response_format
        return body

    def texts(self) -> list[str]:
        return [json.dumps(self.messages), json.dumps(self.tools), json.dumps(self.response_format)]

    def images(self) -> list[bytes]:
        return []


@dataclass
class SparkTurn:
    """One assistant message: ``content`` (text, possibly the final JSON) and ``tool_calls`` in the
    Chat Completions shape ``[{"id", "type": "function", "function": {"name", "arguments": <json str>}}]``."""

    content: str | None
    tool_calls: list[dict] = field(default_factory=list)
    reasoning: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    def as_message(self) -> dict:
        """The assistant message to replay before the tool results (the API requires it)."""
        msg: dict = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg

    def to_json(self) -> dict:
        return {
            "content": self.content,
            "tool_calls": self.tool_calls,
            "reasoning": self.reasoning,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @classmethod
    def from_json(cls, d: dict) -> SparkTurn:
        return cls(
            d["content"],
            d.get("tool_calls", []),
            d.get("reasoning"),
            d.get("input_tokens", 0),
            d.get("output_tokens", 0),
        )


Request = SamRequest | WonderRequest | SparkRequest


def request_images(req: Request) -> list[bytes]:
    return req.image_list() if isinstance(req, WonderRequest) else req.images()


def request_hash(req: Request) -> str:
    """Stable hash of the wire form with images replaced by their digests."""
    body = json.dumps(req.to_wire(images="digest"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()[:24]


def model_of(req: Request) -> str:
    return {SamRequest: "sam", WonderRequest: "wonder", SparkRequest: "spark"}[type(req)]


# ----------------------------------------------------------------------------------------------- backends


class Backend(Protocol):
    name: str

    def sam(self, req: SamRequest) -> SamResult: ...

    def wonder(self, req: WonderRequest) -> WonderResult: ...

    def spark(self, req: SparkRequest) -> SparkTurn: ...


def disc_mask(height: int, width: int, box: Box) -> np.ndarray:
    """A filled ellipse inscribed in the box; what the fake SAM returns."""
    yy, xx = np.mgrid[0:height, 0:width]
    cy, cx = (box.y1 + box.y2) / 2.0, (box.x1 + box.x2) / 2.0
    ry, rx = max((box.y2 - box.y1) / 2.0, 0.5), max((box.x2 - box.x1) / 2.0, 0.5)
    return ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0


def fake_answer(schema: dict, preferred: dict | None = None) -> dict:
    """A record satisfying ``schema`` with nothing committed: enum fields take "unsure" when it exists,
    numbers 0.5, booleans False, strings a note that this is the fake backend."""
    preferred = preferred or {}
    out: dict = {}
    for k, spec in schema.get("properties", {}).items():
        if k in preferred:
            out[k] = preferred[k]
        elif "enum" in spec:
            out[k] = "unsure" if "unsure" in spec["enum"] else spec["enum"][0]
        elif spec.get("type") == "boolean":
            out[k] = False
        elif spec.get("type") in ("number", "integer"):
            lo, hi = spec.get("minimum", 0), spec.get("maximum", 1)
            out[k] = (lo + hi) / 2 if spec.get("type") == "number" else int(lo)
        elif spec.get("type") == "array":
            out[k] = []
        elif spec.get("type") == "object":
            out[k] = fake_answer(spec)
        else:
            out[k] = "fake backend: no opinion"
    return out


class FakeBackend:
    name = "fake"

    def __init__(self, wonder_answers: dict[str, dict] | None = None, spark_script=None):
        self.wonder_answers = wonder_answers or {}
        self.spark_script = spark_script
        self.calls: list[tuple[str, str]] = []

    def sam(self, req: SamRequest) -> SamResult:
        self.calls.append(("sam", request_hash(req)))
        objs = [SamObject(i + 1, b, 0.9, disc_mask(req.height, req.width, b)) for i, b in enumerate(req.boxes)]
        return SamResult(objs, raw_text="fake")

    def wonder(self, req: WonderRequest) -> WonderResult:
        self.calls.append(("wonder", request_hash(req)))
        data = fake_answer(req.schema, self.wonder_answers.get(req.schema_name))
        tokens_in = 1400 * len(req.images) + len(req.question) // 4
        return WonderResult(data, json.dumps(data), tokens_in, 40)

    def spark(self, req: SparkRequest) -> SparkTurn:
        self.calls.append(("spark", request_hash(req)))
        from landers.models.spark import scripted_turn

        return scripted_turn(req, self.spark_script)


class RecordedBackend:
    """Replays saved results keyed by request hash; records new ones when given an inner backend."""

    name = "recorded"

    def __init__(self, directory: Path, inner: Backend | None = None):
        self.dir = Path(directory)
        self.inner = inner
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, req: Request) -> Path:
        return self.dir / f"{model_of(req)}_{request_hash(req)}.json"

    def _fetch(self, req: Request, call, from_json):
        p = self._path(req)
        if p.exists():
            return from_json(json.loads(p.read_text())["result"])
        if self.inner is None:
            raise MissingRecording(f"no recording {p.name}")
        result = call(self.inner)
        p.write_text(json.dumps({"request": req.to_wire(images="digest"), "result": result.to_json()}, indent=1) + "\n")
        return result

    def sam(self, req: SamRequest) -> SamResult:
        return self._fetch(req, lambda b: b.sam(req), SamResult.from_json)

    def wonder(self, req: WonderRequest) -> WonderResult:
        return self._fetch(req, lambda b: b.wonder(req), WonderResult.from_json)

    def spark(self, req: SparkRequest) -> SparkTurn:
        return self._fetch(req, lambda b: b.spark(req), SparkTurn.from_json)


class DryRunBackend:
    """Writes every request it would send, then answers from the inner backend (fake by default)."""

    name = "dry-run"

    def __init__(self, directory: Path, inner: Backend | None = None):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.inner = inner or FakeBackend()
        self.written: list[Path] = []

    def _write(self, req: Request) -> None:
        p = self.dir / f"{model_of(req)}_{request_hash(req)}.json"
        p.write_text(json.dumps({"model": model_of(req), "wire": req.to_wire(images="digest")}, indent=1) + "\n")
        self.written.append(p)

    def sam(self, req: SamRequest) -> SamResult:
        self._write(req)
        return self.inner.sam(req)

    def wonder(self, req: WonderRequest) -> WonderResult:
        self._write(req)
        return self.inner.wonder(req)

    def spark(self, req: SparkRequest) -> SparkTurn:
        self._write(req)
        return self.inner.spark(req)


class RealBackend:
    """The Meta Model API through the ``openai`` SDK. Built only by ``make_backend("real")``."""

    name = "real"

    def __init__(self, api_key: str, base_url: str = BASE_URL):
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - needs the package
            raise RuntimeError("the real backend needs the openai package: uv add openai meta-sam-parser") from e
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    @staticmethod
    def _raise_for(e: Exception):
        status = getattr(e, "status_code", None)
        if status == 400:
            raise RequestError(str(e)[:500]) from e
        if status == 429 or (status is not None and status >= 500):
            raise TransientError(f"status {status}") from e
        raise

    def sam(self, req: SamRequest) -> SamResult:  # pragma: no cover - network
        try:
            from meta_sam_parser import decode_mask_to_raster, image_segmentation_format, parse_responses_stream
        except ImportError as e:
            raise RuntimeError("the real SAM backend needs meta-sam-parser: uv add meta-sam-parser") from e
        try:
            stream = self._client.responses.create(**req.to_wire())
            events = list(stream)
        except Exception as e:
            self._raise_for(e)
        result = parse_responses_stream(events, image_segmentation_format()).final_result()
        raw = "".join(
            getattr(ev, "delta", "") or "" for ev in events if getattr(ev, "type", "") == "response.output_text.delta"
        )
        boxes: dict[int, tuple[Box, float]] = {}
        masks: dict[int, np.ndarray] = {}
        for rec in getattr(result, "records", result):
            oid = int(rec.object_id)
            if rec.kind == "box":
                b = rec.box
                boxes[oid] = (
                    Box(int(b.x1), int(b.y1), int(b.x2), int(b.y2)),
                    float(getattr(rec, "confidence", getattr(b, "c", 0.0)) or 0.0),
                )
            elif rec.kind == "mask":
                small = np.asarray(decode_mask_to_raster(rec.mask), bool)
                masks[oid] = scale_mask(small, req.height, req.width)
        objs = []
        for oid in sorted(set(boxes) | set(masks)):
            box, conf = boxes.get(oid, (Box(0, 0, req.width - 1, req.height - 1), 0.0))
            objs.append(SamObject(oid, box, conf, masks.get(oid, np.zeros((req.height, req.width), bool))))
        return SamResult(objs, raw_text=raw)

    def wonder(self, req: WonderRequest) -> WonderResult:  # pragma: no cover - network
        try:
            r = self._client.chat.completions.create(**req.to_wire())
        except Exception as e:
            self._raise_for(e)
        raw = r.choices[0].message.content or ""
        usage = getattr(r, "usage", None)
        return WonderResult(
            json.loads(raw),
            raw,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def spark(self, req: SparkRequest) -> SparkTurn:  # pragma: no cover - network
        try:
            r = self._client.chat.completions.create(**req.to_wire())
        except Exception as e:
            self._raise_for(e)
        msg = r.choices[0].message
        calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in (msg.tool_calls or [])
        ]
        extra = getattr(msg, "model_extra", None) or {}
        usage = getattr(r, "usage", None)
        return SparkTurn(
            msg.content,
            calls,
            extra.get("reasoning_content"),
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )


def scale_mask(small: np.ndarray, height: int, width: int) -> np.ndarray:
    """Nearest-neighbour scaling of a mask to the image size (the API returns a smaller raster)."""
    h, w = small.shape
    rows = np.minimum((np.arange(height) * h) // max(height, 1), h - 1)
    cols = np.minimum((np.arange(width) * w) // max(width, 1), w - 1)
    return small[rows][:, cols]


def make_backend(kind: str, directory: Path | None = None, env: dict | None = None) -> Backend:
    """``fake``, ``dry-run``, ``recorded`` or ``real``. The real one needs ``MODEL_API_KEY`` and
    ``LANDERS_REAL_CALLS=1`` in the environment, both exported by a person; the key never leaves it."""
    env = os.environ if env is None else env
    if kind == "fake":
        return FakeBackend()
    if kind == "dry-run":
        return DryRunBackend(directory or Path("out/model_requests"))
    if kind == "recorded":
        return RecordedBackend(directory or Path("out/model_recordings"))
    if kind == "real":
        key = env.get("MODEL_API_KEY")
        if not key:
            raise RuntimeError("real backend: MODEL_API_KEY is not in the environment")
        if env.get("LANDERS_REAL_CALLS") != "1":
            raise RuntimeError("real backend: LANDERS_REAL_CALLS=1 is not set; a person must ask for paid calls")
        inner = RealBackend(key)
        return RecordedBackend(directory or Path("out/model_recordings"), inner=inner)
    raise ValueError(f"unknown backend {kind!r}")


# ----------------------------------------------------------------------------------------------- client


class ModelClient:
    """Leak guard, ledger, retries. Every call to a model goes through here."""

    def __init__(self, backend: Backend, ledger: Ledger, sleep=time.sleep, backoff_s: float = 2.0):
        self.backend = backend
        self.ledger = ledger
        self.ledger.backend = backend.name
        self.sleep = sleep
        self.backoff_s = backoff_s
        self.log: list[dict] = []

    def _guard(self, req: Request) -> None:
        for i, t in enumerate(req.texts()):
            leak.check_text(t, f"{model_of(req)} text[{i}]")
        for i, png in enumerate(request_images(req)):
            leak.check_png(png, f"{model_of(req)} image[{i}]")

    def _call(self, req: Request, units: int, fn) -> Any:
        self._guard(req)
        model = model_of(req)
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.ledger.charge(model, units)
            try:
                result = fn()
            except TransientError as e:
                self.ledger.record(model, ok=False)
                self.log.append({"model": model, "hash": request_hash(req), "attempt": attempt, "transient": str(e)})
                last = e
                self.sleep(self.backoff_s * attempt)
                continue
            except Exception:
                self.ledger.record(model, ok=False)
                raise
            self.ledger.record(model, True, getattr(result, "input_tokens", 0), getattr(result, "output_tokens", 0))
            self.log.append({"model": model, "hash": request_hash(req), "attempt": attempt, "ok": True})
            return result
        raise RuntimeError(f"{model}: gave up after {MAX_ATTEMPTS} attempts") from last

    def sam(self, req: SamRequest) -> SamResult:
        return self._call(req, 1, lambda: self.backend.sam(req))

    def wonder(self, req: WonderRequest) -> WonderResult:
        return self._call(req, 1, lambda: self.backend.wonder(req))

    def spark(self, req: SparkRequest) -> SparkTurn:
        return self._call(req, 1, lambda: self.backend.spark(req))
