"""The ledger: every model call counted against a hard cap, with a running cost estimate.

Units: SAM counts images, Wonder counts calls, Spark counts turns. A call is charged before it is made and
every attempt (a 429 retried, a failure) stays counted. ``LANDERS_CAP_SAM``, ``LANDERS_CAP_WONDER`` and
``LANDERS_CAP_SPARK`` override the caps. The ledger is the only thing that may refuse a call for cost, and
nothing else may bypass it.

Prices (docs/models.md, Oct 2026) are estimates for the person reading the ledger, not a bill.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

MODELS = ("sam", "wonder", "spark")
UNIT = {"sam": "images", "wonder": "calls", "spark": "turns"}
DEFAULT_CAPS = {"sam": 3000, "wonder": 300, "spark": 200}
PRICES_USD = {
    "sam": {"per_unit": 2.50 / 1000},
    "wonder": {"input_token": 4.0 / 1e6, "output_token": 20.0 / 1e6},
    "spark": {"input_token": 1.25 / 1e6, "output_token": 4.25 / 1e6},
}


class CapError(RuntimeError):
    """The hard cap would be passed. The call is not made."""


def caps_from_env(base: dict | None = None) -> dict:
    caps = dict(base or DEFAULT_CAPS)
    for m in MODELS:
        v = os.environ.get(f"LANDERS_CAP_{m.upper()}")
        if v is not None:
            caps[m] = int(v)
    return caps


def _blank() -> dict:
    return {
        "units": 0,
        "attempts": 0,
        "ok": 0,
        "failed": 0,
        "refused": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }


@dataclass
class Ledger:
    path: Path | None = None
    caps: dict = field(default_factory=caps_from_env)
    entries: dict = field(default_factory=lambda: {m: _blank() for m in MODELS})
    backend: str = ""
    started: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    @classmethod
    def load(cls, path: Path, caps: dict | None = None) -> Ledger:
        """Continue a ledger from disk (counts carry over); a fresh one when the file is absent."""
        path = Path(path)
        led = cls(path=path, caps=caps or caps_from_env())
        if path.exists():
            d = json.loads(path.read_text())
            for m in MODELS:
                led.entries[m].update(d.get("entries", {}).get(m, {}))
        return led

    def remaining(self, model: str) -> int:
        return self.caps[model] - self.entries[model]["units"]

    def charge(self, model: str, units: int = 1) -> None:
        """Reserve ``units`` before a call. Raises CapError, and records the refusal, when over the cap."""
        if model not in MODELS:
            raise KeyError(model)
        e = self.entries[model]
        if e["units"] + units > self.caps[model]:
            e["refused"] += 1
            self.save()
            raise CapError(f"{model}: {e['units']} + {units} {UNIT[model]} would pass the cap of {self.caps[model]}")
        e["units"] += units
        e["attempts"] += 1
        if model == "sam":
            e["cost_usd"] += units * PRICES_USD["sam"]["per_unit"]
        self.save()

    def record(self, model: str, ok: bool, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Outcome of a charged attempt; tokens add to the cost estimate."""
        e = self.entries[model]
        e["ok" if ok else "failed"] += 1
        e["input_tokens"] += int(input_tokens)
        e["output_tokens"] += int(output_tokens)
        p = PRICES_USD[model]
        if "input_token" in p:
            e["cost_usd"] += input_tokens * p["input_token"] + output_tokens * p["output_token"]
        self.save()

    def total_cost_usd(self) -> float:
        return round(sum(e["cost_usd"] for e in self.entries.values()), 4)

    def to_json(self) -> dict:
        return {
            "started": self.started,
            "backend": self.backend,
            "caps": self.caps,
            "units": UNIT,
            "entries": {m: {**e, "cost_usd": round(e["cost_usd"], 4)} for m, e in self.entries.items()},
            "total_cost_usd": self.total_cost_usd(),
        }

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_json(), indent=1) + "\n")
