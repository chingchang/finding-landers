"""Run the physical detector over strips and write a candidates file for scripts/score.py.

    uv run scripts/detect.py <observation id> --run try1
    uv run scripts/detect.py --site viking1 --sites controls/sites.json --max-tiles 20

Output: out/candidates_<run>.json, rewritten after every strip so a killed run keeps the strips it finished;
``--resume`` reruns only the strips that file does not have yet. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.detect import DetectorConfig, detect_strip, detect_strip_parallel  # noqa: E402
from landers.strip import Strip  # noqa: E402

DEFAULT_CAL = config.REPO_ROOT / "landers" / "calibration_v0.json"
_RULE_FILES = sorted((config.REPO_ROOT / "landers").glob("shape_v*.json"))
DEFAULT_RULES = _RULE_FILES[-1] if _RULE_FILES else config.REPO_ROOT / "landers" / "shape_v1.json"


def repo_relative(path: str) -> str:
    """A path recorded by its place inside the repo, not this machine's, when it is inside the repo."""
    p = Path(path).resolve()
    return str(p.relative_to(config.REPO_ROOT)) if p.is_relative_to(config.REPO_ROOT) else path


def write_result(path: Path, result: dict) -> None:
    """Write the whole file to a sibling and rename it into place, so a reader never sees a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(result, indent=1))
    os.replace(tmp, path)


def resume_from(path: Path, result: dict) -> dict:
    """The strips an earlier, interrupted run of the same name and detector config already wrote."""
    if not path.exists():
        return result
    old = json.loads(path.read_text())
    if old.get("detector") != json.loads(json.dumps(result["detector"])):  # tuples read back as lists
        raise SystemExit(f"{path}: detector config differs from this run's; not resuming")
    result["strips"] = dict(old.get("strips", {}))
    result["resumed_from"] = {"started": old.get("started"), "git_commit": old.get("git_commit")}
    return result


def git_commit() -> str:
    """The commit the run's code comes from; LANDERS_COMMIT overrides it when running from a frozen export."""
    if os.environ.get("LANDERS_COMMIT"):
        return os.environ["LANDERS_COMMIT"]
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
    ap.add_argument(
        "--per-strip",
        action="store_true",
        help="v0.4: calibrate each strip from its own candidate population after the raw pass (landers/calibrate.py "
        "fit_strip) instead of the table; the fitted curves are recorded in the strip's entry",
    )
    ap.add_argument(
        "--top-exclude", type=int, default=0, help="per-strip: top candidates per branch left out of the knots"
    )
    ap.add_argument(
        "--min-population",
        type=int,
        default=0,
        help="per-strip: a branch with fewer candidates than this on a strip is scored by the --calibration table",
    )
    ap.add_argument(
        "--shape-rules",
        default=str(DEFAULT_RULES) if DEFAULT_RULES.exists() else None,
        help="shape rules JSON (landers/shape.py); default: the newest landers/shape_v*.json if any",
    )
    ap.add_argument("--no-shape-rules", action="store_true", help="record shape features, add nothing to the score")
    ap.add_argument("--legacy-saturation", action="store_true", help="v0.1 behaviour: saturated pixels are no-data")
    ap.add_argument(
        "--sheet-flatness",
        type=float,
        default=None,
        help="item 8b: the sheet branch's flatness threshold (default 0.45)",
    )
    ap.add_argument(
        "--sheet-saturated-as-data",
        action="store_true",
        help="item 8b: saturated pixels are data in the sheet branch too",
    )
    ap.add_argument("--jobs", type=int, default=1, help="worker processes per strip (3 at most on 8 GB)")
    ap.add_argument("--out", default=str(config.REPO_ROOT / "out"))
    ap.add_argument("--resume", action="store_true", help="skip strips already in out/candidates_<run>.json")
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
    cal = None if a.no_calibration else a.calibration  # per-strip: the fallback table for thin branches
    rules = None if a.no_shape_rules else a.shape_rules
    saturated_is_data = not a.legacy_saturation
    mode = (
        {
            "calibration_mode": "per_strip",
            "calibration_top_exclude": a.top_exclude,
            "calibration_min_population": a.min_population,
        }
        if a.per_strip
        else {}
    )
    if a.sheet_flatness is not None:
        mode["sheet_flatness"] = a.sheet_flatness
    if a.sheet_saturated_as_data:
        mode["sheet_saturated_is_data"] = True
    # cfg is what the file records (paths inside the repo); cfg_run is what runs (absolute paths)
    cfg = DetectorConfig(
        frozen=a.frozen,
        calibration=repo_relative(cal) if cal else None,
        shape_rules=repo_relative(rules) if rules else None,
        saturated_is_data=saturated_is_data,
        **mode,
    )
    cfg_run = DetectorConfig(
        frozen=a.frozen,
        calibration=str(Path(cal).resolve()) if cal else None,
        shape_rules=str(Path(rules).resolve()) if rules else None,
        saturated_is_data=saturated_is_data,
        **mode,
    )
    result = {
        "run": a.run,
        "detector": cfg.to_json(),
        "git_commit": git_commit(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "strips": {},
    }
    out = Path(a.out) / f"candidates_{a.run}.json"
    if a.resume:
        result = resume_from(out, result)
    for sid in ids:
        if config.find_strip(sid) is None:
            print(f"{sid}: not on disk, skipped")
            continue
        if sid in result["strips"]:
            print(f"{sid}: already in {out}, skipped")
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
        write_result(out, result)  # after every strip, so an interrupted run keeps what it finished
    write_result(out, result)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
