"""The search pass itself, one strip at a time, so a session that ends early loses one strip, not the run.

Nothing here is called by the bookkeeping; ``scripts/search.py run`` calls it for item 11, with the detector
frozen. Each strip's candidates go to their own file with the commit and tag they came from.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from landers import config
from landers.detect import DetectorConfig, detect_strip, detect_strip_parallel
from landers.strip import Strip


def git_state() -> dict:
    """Commit, whether the tree is dirty, and the exact tag on HEAD if there is one."""

    def run(*args):
        try:
            r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=config.REPO_ROOT)
            return r.stdout.strip() if r.returncode == 0 else None
        except OSError:
            return None

    commit = run("rev-parse", "HEAD")
    dirty = bool(run("status", "--porcelain", "--untracked-files=no"))
    return {"commit": commit, "dirty": dirty, "tag": run("describe", "--tags", "--exact-match")}


# What the held-out run compared against the tag (docs/reports/2026-10-29-heldout-run.md): the detector, its
# driver, the thresholds and the locked dependencies. This package is left out: nothing outside it imports
# it, and it only drives the detector and writes the files.
FROZEN_PATHS = (
    "landers",
    ":(exclude)landers/search",
    "scripts/detect.py",
    "controls/thresholds.json",
    "pyproject.toml",
    "uv.lock",
)


def code_matches_tag(tag: str, paths=FROZEN_PATHS) -> bool | None:
    """True when HEAD's ``paths`` are byte for byte the tag's; None when the tag is unknown."""
    try:
        known = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"],
                               capture_output=True, cwd=config.REPO_ROOT)
        if known.returncode != 0:
            return None
        r = subprocess.run(["git", "diff", "--quiet", f"{tag}^{{commit}}", "HEAD", "--", *paths],
                           capture_output=True, cwd=config.REPO_ROOT)
    except OSError:
        return None
    return r.returncode == 0


def repo_relative(path: str | None) -> str | None:
    if path is None:
        return None
    p = Path(path).resolve()
    return str(p.relative_to(config.REPO_ROOT)) if p.is_relative_to(config.REPO_ROOT) else str(path)


def frozen_configs(calibration: str | None, shape_rules: str | None) -> tuple[DetectorConfig, DetectorConfig]:
    """The frozen detector as scripts/detect.py --frozen builds it with its defaults (table calibration, the
    newest shape rules, saturated pixels as data): one config to record (paths inside the repo), one to run
    (absolute paths, so the workers find the files from any directory)."""
    rec = DetectorConfig(frozen=True, calibration=repo_relative(calibration), shape_rules=repo_relative(shape_rules))
    run_cfg = DetectorConfig(
        frozen=True,
        calibration=str(Path(calibration).resolve()) if calibration else None,
        shape_rules=str(Path(shape_rules).resolve()) if shape_rules else None,
    )
    return rec, run_cfg


def strip_output(out_dir: Path, observation_id: str) -> Path:
    return Path(out_dir) / f"candidates_{observation_id}.json"


def run_strip(
    observation_id: str,
    cfg: DetectorConfig,
    out_dir: Path,
    jobs: int = 1,
    detector=None,
    progress=None,
    record_cfg: DetectorConfig | None = None,
    same_code_as: str | None = None,
):
    """Detect over one strip and write its file. ``detector`` replaces the real pass in tests; ``record_cfg``
    is what the file records when it differs from ``cfg`` only by where the files are."""
    strip = Strip.open(observation_id)
    t = time.time()
    if detector is not None:
        entry = detector(strip, cfg)
    elif jobs > 1:
        entry = detect_strip_parallel(strip, cfg, jobs, progress=progress)
    else:
        entry = detect_strip(strip, cfg, progress=progress)
    result = {
        "run": "search",
        "detector": (record_cfg or cfg).to_json(),
        "git": {**git_state(), **({"same_code_as": same_code_as} if same_code_as else {})},
        "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)),
        "seconds": round(time.time() - t),
        "strips": {observation_id: entry},
    }
    out = strip_output(out_dir, observation_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.part")
    tmp.write_text(json.dumps(result, indent=1))
    tmp.replace(out)
    return out, entry


def pending(ids: list[str], out_dir: Path) -> list[str]:
    """Ids with no finished file yet, in the given order."""
    return [sid for sid in ids if not strip_output(out_dir, sid).exists()]
