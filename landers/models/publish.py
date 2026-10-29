"""Copy a model run's results into the repository, blind.

The scripts write under ``out/`` (ignored by git). What is committed with a report is the ledger, the
per-stage records and the tool log, never the id-to-position manifests or the input lists. A vision
model's free text can name any place it likes, including a sealed site; ``redact`` replaces the name of
every held-out and final-exam site (from ``controls/sites.json``) with a fixed marker and counts the
replacements, so the committed copy passes ``scripts/leakcheck.sh`` and the report can say how many
answers were changed and nothing else about them. Numbers are never changed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from landers.models import leak

MARKER = "[sealed site name]"
SEALED_GROUPS = ("heldout", "final_exam")
PUBLISHED = ("ledger.json", "probe_*.json", "votes_*.json", "sam_*.json", "review_*.json", "model_recordings/*.json")
NEVER = ("manifest_",)


def sealed_names() -> list[str]:
    """Names of the sealed sites, with their trailing digits dropped as well (``viking2`` and ``viking``)."""
    p = leak.sites_path()
    if not p.exists():
        return []
    names: set[str] = set()
    for s in json.loads(p.read_text())["sites"]:
        if s.get("group") in SEALED_GROUPS:
            names.add(s["name"])
            names.add(re.sub(r"\d+$", "", s["name"]))
    return sorted(n for n in names if n)


def redact(obj, patterns: list[re.Pattern] | None = None) -> tuple[object, int]:
    """``obj`` with every sealed-site name in any string replaced by ``MARKER``; returns the count."""
    if patterns is None:
        patterns = [re.compile(r"\b" + re.escape(n) + r"\b", re.I) for n in sealed_names()]
    if isinstance(obj, str):
        n = 0
        for pat in patterns:
            obj, k = pat.subn(MARKER, obj)
            n += k
        return obj, n
    if isinstance(obj, dict):
        out, n = {}, 0
        for k, v in obj.items():
            v2, k2 = redact(v, patterns)
            out[k] = v2
            n += k2
        return out, n
    if isinstance(obj, list):
        items = [redact(v, patterns) for v in obj]
        return [v for v, _ in items], sum(k for _, k in items)
    return obj, 0


def publish(src: Path, dst: Path) -> dict:
    """Copy the published files of ``src`` into ``dst`` (made fresh), redacted. Returns the record that is
    also written to ``dst/PUBLISHED.json``: source, files, redactions per file."""
    src, dst = Path(src), Path(dst)
    files: list[Path] = []
    for pattern in PUBLISHED:
        files.extend(p for p in sorted(src.glob(pattern)) if not p.name.startswith(NEVER))
    dst.mkdir(parents=True, exist_ok=True)
    record: dict = {"source": str(src), "marker": MARKER, "files": {}}
    for p in files:
        obj, n = redact(json.loads(p.read_text()))
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(obj, indent=1) + "\n")
        record["files"][str(rel)] = {"redactions": n}
    record["total_redactions"] = sum(f["redactions"] for f in record["files"].values())
    (dst / "PUBLISHED.json").write_text(json.dumps(record, indent=1) + "\n")
    return record
