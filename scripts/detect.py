"""Run the physical detector over strips and write a candidates file for scripts/score.py.

    uv run scripts/detect.py <observation id> --run try1
    uv run scripts/detect.py --site viking1 --sites controls/sites.json --max-tiles 20

Output: out/candidates_<run>.json. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.detect import DetectorConfig, detect_strip, detect_strip_parallel  # noqa: E402
from landers.strip import Strip  # noqa: E402

DEFAULT_CAL = config.REPO_ROOT / "landers" / "calibration_v0.json"


def git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=config.REPO_ROOT)
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            cwd=config.REPO_ROOT,
        )
        return r.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except OSError:
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="observation ids")
    ap.add_argument("--site", action="append", default=[], help="all strips of a site from the sites file")
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--run", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--max-tiles", type=int, default=None)
    ap.add_argument("--frozen", action="store_true", help="mark this run's detector as frozen (person only)")
    ap.add_argument(
        "--calibration",
        default=str(DEFAULT_CAL) if DEFAULT_CAL.exists() else None,
        help="calibration JSON from scripts/calibrate.py (default: landers/calibration_v0.json if present)",
    )
    ap.add_argument("--no-calibration", action="store_true", help="raw branch scores")
    ap.add_argument("--jobs", type=int, default=1, help="worker processes per strip (3 at most on 8 GB)")
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out"))
    a = ap.parse_args(argv)

    ids = list(a.ids)
    if a.site:
        sites = {s["name"]: s for s in json.loads(Path(a.sites).read_text())["sites"]}
        for name in a.site:
            s = sites[name]
            if s["group"] in ("heldout", "final_exam") and not a.frozen:
                print(f"{name} is {s['group']}: refused unless the detector is frozen", file=sys.stderr)
                return 3
            ids.extend(s["strips"])
    if not ids:
        ap.error("no strips given")
    cal = None if a.no_calibration else a.calibration
    cfg = DetectorConfig(frozen=a.frozen, calibration=cal)
    if cal:  # record the calibration by its path inside the repo, not this machine's
        cfg.calibration = (
            str(Path(cal).resolve().relative_to(config.REPO_ROOT))
            if Path(cal).resolve().is_relative_to(config.REPO_ROOT)
            else cal
        )
        cfg_run = DetectorConfig(frozen=a.frozen, calibration=str(Path(cal).resolve()))
    else:
        cfg_run = cfg
    result = {
        "run": a.run,
        "detector": cfg.to_json(),
        "git_commit": git_commit(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "strips": {},
    }
    for sid in ids:
        if config.find_strip(sid) is None:
            print(f"{sid}: not on disk, skipped")
            continue
        strip = Strip.open(sid)
        t = time.time()
        prog = lambda n, k, sid=sid: print(f"\r{sid} tiles={n} cands={k}", end="", flush=True)  # noqa: E731
        if a.jobs > 1:
            entry = detect_strip_parallel(strip, cfg_run, a.jobs, a.max_tiles, progress=prog)
        else:
            entry = detect_strip(strip, cfg_run, a.max_tiles, progress=prog)
        print(f"\r{sid}: {len(entry['candidates'])} candidates from {entry['tiles']} tiles in {time.time() - t:.0f}s")
        result["strips"][sid] = entry
    out = Path(a.out) / f"candidates_{a.run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
