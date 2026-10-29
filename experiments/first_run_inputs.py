"""Inputs for the first real model run (plan item 9b), cut once so the scripts need not load the 150 MB
candidate file each time.

    uv run experiments/first_run_inputs.py <candidates.json> --strips ESP_... ESP_... --out out/models/inputs

Writes ``candidates_first_run.json`` (the top ``--keep`` candidates by score of each named strip, in the
detector's own format with its ``run`` and ``detector`` fields) and ``key_pieces.json`` (the recorded
pieces of the same strips from ``controls/tuning.json`` in the same format, grade "not assessed", for the
recognition probe at the places a vision model is most likely to know). Both stay under ``out/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers import config  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--strips", nargs="+", required=True)
    ap.add_argument("--keep", type=int, default=200)
    ap.add_argument("--key", default=str(config.REPO_ROOT / "controls" / "tuning.json"))
    ap.add_argument("--out", default="out/models/inputs")
    a = ap.parse_args(argv)

    data = json.loads(Path(a.candidates).read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    strips = {}
    for sid in a.strips:
        s = data["strips"][sid]
        top = sorted(s["candidates"], key=lambda c: -c["score"])[: a.keep]
        strips[sid] = {**{k: v for k, v in s.items() if k != "candidates"}, "candidates": top}
        print(f"{sid}: kept {len(top)} of {len(s['candidates'])}")
    head = {k: v for k, v in data.items() if k != "strips"}
    (out / "candidates_first_run.json").write_text(
        json.dumps({**head, "source": str(a.candidates), "strips": strips}, indent=1) + "\n"
    )

    key = json.loads(Path(a.key).read_text())
    pieces = {}
    for site in key["sites"]:
        for pc in site["pieces"]:
            if pc.get("strip") not in a.strips or pc.get("line") is None:
                continue
            scale = 0.5 if pc["strip"].endswith("_1995") else 0.25  # 50 cm/px strip is the only exception
            r = (pc.get("size_m") or 2.0) / scale / 2.0
            pieces.setdefault(pc["strip"], []).append(
                {
                    "row": float(pc["line"]) - 1.0,
                    "col": float(pc["sample"]) - 1.0,
                    "score": 0.0,
                    "branch": "bright",
                    "grade": "not assessed",
                    "area_px": int(3.14159 * r * r),
                    "extra": {"piece": f"{site['name']}:{pc['piece']}"},
                }
            )
    (out / "key_pieces.json").write_text(
        json.dumps(
            {
                "run": "key_pieces",
                "note": "recorded pieces from controls/tuning.json as candidates for the recognition probe; "
                "score 0 keeps the list order as the key lists them",
                "strips": {sid: {"candidates": cs} for sid, cs in pieces.items()},
            },
            indent=1,
        )
        + "\n"
    )
    for sid, cs in pieces.items():
        print(f"{sid}: {len(cs)} recorded pieces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
