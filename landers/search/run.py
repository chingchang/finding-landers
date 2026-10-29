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


def strip_output(out_dir: Path, observation_id: str) -> Path:
    return Path(out_dir) / f"candidates_{observation_id}.json"


def run_strip(observation_id: str, cfg: DetectorConfig, out_dir: Path, jobs: int = 1, detector=None, progress=None):
    """Detect over one strip and write its file. ``detector`` replaces the real pass in tests."""
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
        "detector": cfg.to_json(),
        "git": git_state(),
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
