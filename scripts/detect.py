"""Run the physical detector over strips and write a candidates file for scripts/score.py.

    uv run scripts/detect.py <observation id> --run try1
    uv run scripts/detect.py --site viking1 --sites controls/sites.json --max-tiles 20

Output: out/candidates_<run>.json. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402
from landers.detect import DetectorConfig, detect_strip  # noqa: E402
from landers.strip import Strip  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="observation ids")
    ap.add_argument("--site", action="append", default=[], help="all strips of a site from the sites file")
    ap.add_argument("--sites", default=str(config.REPO_ROOT / "controls" / "sites.json"))
    ap.add_argument("--run", default=time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--max-tiles", type=int, default=None)
    ap.add_argument("--frozen", action="store_true", help="mark this run's detector as frozen (person only)")
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
    cfg = DetectorConfig(frozen=a.frozen)
    result = {"run": a.run, "detector": cfg.to_json(), "strips": {}}
    for sid in ids:
        if config.find_strip(sid) is None:
            print(f"{sid}: not on disk, skipped")
            continue
        strip = Strip.open(sid)
        t = time.time()
        entry = detect_strip(
            strip, cfg, a.max_tiles, progress=lambda n, k, sid=sid: print(f"\r{sid} tiles={n} cands={k}", end="")
        )
        print(f"\r{sid}: {len(entry['candidates'])} candidates from {entry['tiles']} tiles in {time.time() - t:.0f}s")
        result["strips"][sid] = entry
    out = Path(a.out) / f"candidates_{a.run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
