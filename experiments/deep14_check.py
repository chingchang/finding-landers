"""Checks on item 14's dry run, no model call.

    uv run experiments/deep14_check.py --dry out/deep14_dry

1. Every request text in the dry run, scanned again: observation ids, sealed and tuning site names, dates, file names.
2. An exported crop against the strip: the 256 px views of a sample of candidates, drawn from both, must be the same pixels,
   so a vote from the export is the vote the strip would give.
3. How many of the voted crops hold a saturated pixel near the centre, so the new drawing is measured, not assumed.
4. One saturated crop written out both ways, old and new, for a person's eye.

Writes out/deep14/dry_check.json and out/deep14/saturated_old_new.png.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
import deep14_run as drv  # noqa: E402

from landers.models import crops  # noqa: E402
from landers.strip import SATURATED, Strip  # noqa: E402
from scripts.models_sam import strip_reader  # noqa: E402

SAMPLE_PER_STRIP = 3


def texts_of(doc) -> list[str]:
    out = []
    if isinstance(doc, dict):
        for v in doc.values():
            out += texts_of(v)
    elif isinstance(doc, list):
        for v in doc:
            out += texts_of(v)
    elif isinstance(doc, str):
        out.append(doc)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", required=True)
    a = ap.parse_args()
    dry = Path(a.dry)
    sites = json.loads((ROOT / "controls/sites.json").read_text())
    names = sorted({s["name"] for s in sites["sites"]})
    patterns = {
        "observation id": re.compile(r"\b(ESP|PSP)_\d{6}_\d{4}\b"),
        "date": re.compile(r"\b(19|20)\d\d-\d\d-\d\d\b"),
        "file name": re.compile(r"\.(JP2|LBL|npz|json|png)\b", re.I),
        "site name": re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b", re.I),
    }
    requests = sorted((dry / "model_requests").iterdir())
    hits: dict = {k: [] for k in patterns}
    kinds: Counter = Counter()
    distinct: Counter = Counter()
    images: Counter = Counter()
    for f in requests:
        doc = json.loads(f.read_text())["wire"]
        kinds[f.name.split("_")[0]] += 1
        for t in texts_of(doc):
            if t.startswith("data:"):
                continue
            for name, pat in patterns.items():
                if pat.search(t):
                    hits[name].append({"file": f.name, "text": pat.search(t).group(0)})
        if f.name.startswith("wonder"):
            content = doc["messages"][0]["content"]
            distinct[content[0]["text"]] += 1
            images[sum(c["type"] == "image_url" for c in content)] += 1

    data = drv.load(drv.INPUTS / "candidates_combined.json")
    same, compared = 0, 0
    with_sat, voted = {}, {}
    sat_example = None
    for sid, s in data["strips"].items():
        cands = s["candidates"][:100]
        bank = drv.CropBank(sid, cands)
        strip = Strip.open(sid)
        reader = strip_reader(strip)
        for c in cands[:: len(cands) // SAMPLE_PER_STRIP][:SAMPLE_PER_STRIP]:
            d0, v0 = reader(c["row"], c["col"], 320)
            d1, v1 = bank.read(c["row"], c["col"], 320)
            compared += 1
            same += bool(np.array_equal(d0, d1) and np.array_equal(v0, v1))
        n = 0
        for c in cands:
            d, _ = bank.read(c["row"], c["col"], 64)
            if (d >= SATURATED).any():
                n += 1
                if sat_example is None:
                    sat_example = (sid, c)
        with_sat[sid], voted[sid] = n, len(cands)

    if sat_example:
        sid, c = sat_example
        d, v = drv.CropBank(sid, [c]).read(c["row"], c["col"], 320)
        arr, ok = crops.square_crop(d, v, 160, 160, 64)
        old = crops.stretch(arr, ok, 0.5, 99.5)
        new = crops.stretch(arr, ok, 0.5, 99.5, saturated_bright=True)
        pair = np.concatenate([old, np.full((64, 4), 128, np.uint8), new], axis=1)
        Image.fromarray(np.repeat(np.repeat(pair, 6, axis=0), 6, axis=1)).save(ROOT / "out/deep14/saturated_old_new.png")

    out = {
        "requests": len(requests),
        "by_kind": dict(kinds),
        "leak_hits": {k: len(v) for k, v in hits.items()},
        "leak_examples": {k: v[:5] for k, v in hits.items()},
        "distinct_wonder_questions": {t[:80]: n for t, n in distinct.items()},
        "images_per_wonder_request": {str(k): v for k, v in images.items()},
        "export_equals_strip": {"compared": compared, "same_pixels": same},
        "crops_with_saturated_pixels_in_centre_64px": with_sat,
        "crops_voted": voted,
    }
    (ROOT / "out/deep14/dry_check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
