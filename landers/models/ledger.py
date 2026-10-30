"""The ledger: every model call counted against a hard cap, with a running cost estimate.

Units: SAM counts images, Wonder counts calls, Spark counts turns. A call is charged before it is made and
every attempt (a 429 retried, a failure) stays counted. ``LANDERS_CAP_SAM``, ``LANDERS_CAP_WONDER`` and
``LANDERS_CAP_SPARK`` override the caps. The ledger is the only thing that may refuse a call for cost, and
nothing else may bypass it.

Three more limits sit here for the same reason (Decisions of 2026-10-30 07:00 in docs/plan.md):

- The cumulative dollar cap: every run's ledger is listed in docs/reports/ledgers.json, and a call is refused once the
  total over those ledgers would pass ``TOTAL_CAP_USD``. ``LANDERS_CAP_TOTAL_USD`` can lower the cap, never raise it.
- The pause: a run may name a total of calls after which it stops, so a person can compare the ledger with the bill.
- Reservations: calls set aside for one purpose (the strips' votes), which no other call may spend.

Prices (docs/models.md, Oct 2026) are estimates for the person reading the ledger, not a bill.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
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
TOTAL_CAP_USD = 120.0  # the 150 USD credit less the gap for a possible Wonder token undercount; a person's number
# The most one more call is assumed to add, so "would pass" can be checked before the tokens are known. The largest Wonder
# vote in item 9c took 1,864 output tokens, about 0.04 USD (docs/reports/2026-10-30-deep-pass/vote_stats_9c.json).
NEXT_CALL_USD = {"sam": PRICES_USD["sam"]["per_unit"], "wonder": 0.05, "spark": 0.05}
REGISTER = Path(__file__).resolve().parent.parent.parent / "docs" / "reports" / "ledgers.json"


class CapError(RuntimeError):
    """The hard cap would be passed. The call is not made."""


class PauseError(CapError):
    """The run reached its pause: a person compares the ledger with the bill before it goes on."""


def total_cap_from_env() -> float:
    v = os.environ.get("LANDERS_CAP_TOTAL_USD")
    return TOTAL_CAP_USD if v is None else min(float(v), TOTAL_CAP_USD)


def spent_usd(register: Path = REGISTER, exclude: Path | None = None) -> float:
    """The total over every ledger on the register, less the one at ``exclude`` (the run that is asking). A listed ledger
    that is missing raises, unless it is marked live and has not started: a total that silently leaves a run out is the
    failure this exists to prevent."""
    register = Path(register)
    root = register.parent.parent.parent
    total = 0.0
    for row in json.loads(register.read_text())["ledgers"]:
        path = (root / row["path"]).resolve()
        if exclude is not None and path == Path(exclude).resolve():
            continue
        if not path.exists():
            if row.get("live"):
                continue
            raise FileNotFoundError(f"ledger of item {row['item']} is listed but missing: {row['path']}")
        total += float(json.loads(path.read_text())["total_cost_usd"])
    return round(total, 4)


def register_run(path: Path, item: str, register: Path = REGISTER) -> None:
    """List a paid run's ledger before its first call. A ledger already listed stays as it is."""
    register = Path(register)
    root = register.parent.parent.parent
    doc = json.loads(register.read_text())
    if any((root / r["path"]).resolve() == Path(path).resolve() for r in doc["ledgers"]):
        return
    rel = Path(path).resolve().relative_to(root.resolve()).as_posix()
    doc["ledgers"].append({"item": item, "path": rel, "live": True})
    register.write_text(json.dumps(doc, indent=1) + "\n")


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
    prior_usd: float = 0.0  # what every other ledger on the register has spent
    total_cap_usd: float = field(default_factory=total_cap_from_env)
    pause_at_units: int | None = None  # this ledger's calls over all models at which the run stops
    reserved: dict = field(default_factory=dict)  # model -> calls only a ``spending_reserved`` block may use
    _in_reserve: bool = False

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

    def units_total(self) -> int:
        return sum(e["units"] for e in self.entries.values())

    def reserve(self, model: str, units: int) -> None:
        """Set calls aside. Refused when the cap cannot hold them, before anything is sent."""
        if units > self.remaining(model):
            raise CapError(f"{model}: cannot reserve {units} {UNIT[model]}, {self.remaining(model)} remain under the cap")
        self.reserved[model] = units

    @contextmanager
    def spending_reserved(self) -> Iterator[None]:
        """Calls made inside this block draw on the reservation."""
        self._in_reserve = True
        try:
            yield
        finally:
            self._in_reserve = False

    def _refuse(self, model: str, why: str, kind: type[CapError] = CapError) -> None:
        self.entries[model]["refused"] += 1
        self.save()
        raise kind(why)

    def charge(self, model: str, units: int = 1) -> None:
        """Reserve ``units`` before a call. Raises CapError, and records the refusal, when over a cap."""
        if model not in MODELS:
            raise KeyError(model)
        e = self.entries[model]
        if self.pause_at_units is not None and self.units_total() + units > self.pause_at_units:
            self._refuse(model, f"paused at {self.pause_at_units} calls for a person to check the bill", PauseError)
        if e["units"] + units > self.caps[model]:
            self._refuse(model, f"{model}: {e['units']} + {units} {UNIT[model]} would pass the cap of {self.caps[model]}")
        held = self.reserved.get(model, 0)
        if not self._in_reserve and e["units"] + units + held > self.caps[model]:
            self._refuse(model, f"{model}: {held} {UNIT[model]} are reserved; this call may not spend them")
        running = self.prior_usd + sum(x["cost_usd"] for x in self.entries.values())
        if running + units * NEXT_CALL_USD[model] > self.total_cap_usd:
            self._refuse(model, f"{model}: {running:.4f} USD so far over all runs; the next call would pass {self.total_cap_usd}")
        if self._in_reserve and held:
            self.reserved[model] = max(0, held - units)
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
            "prior_usd": self.prior_usd,
            "total_cap_usd": self.total_cap_usd,
        }

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_json(), indent=1) + "\n")
