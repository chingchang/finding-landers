"""Driver for the model-layer scoreboard (plan item 9c): per strip, Wonder votes on the top 10, SAM on the
top 20, one Spark review of the top 20, all on one ledger in ``--out-dir``.

    uv run --env-file out/caps.env experiments/scoreboard_run.py out/scoreboard/inputs/candidates_frozen_v1.json \
        --reference <strip> --reference-for-reference <strip> --backend dry-run --out-dir out/scoreboard_dry
    uv run --env-file out/caps.env experiments/scoreboard_run.py ... --backend real --out-dir out/scoreboard

Resumable: a stage whose output file exists is skipped, and a stage that died part way is rerun with the
real backend answering every request it already sent from ``model_recordings/`` (the ledger still counts
those units, so it overstates rather than understates). The reference crop for the votes comes from
``--reference`` (item 9c used the Spirit strip, as item 9b did) and from ``--reference-for-reference`` for
that strip itself; the report names both.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import models_review, models_sam, models_wonder  # noqa: E402

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates")
    ap.add_argument("--backend", required=True, choices=models_sam.BACKENDS)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--reference", required=True, help="strip the reference crop comes from")
    ap.add_argument("--reference-for-reference", required=True, help="reference crop for the --reference strip")
    ap.add_argument("--strips", nargs="*", default=None, help="default: every strip in the file, in file order")
    a = ap.parse_args(argv)

    strips = a.strips or list(json.loads(Path(a.candidates).read_text())["strips"])
    out = Path(a.out_dir)
    common = [a.candidates, "--backend", a.backend, "--out-dir", str(out)]
    for sid in strips:
        ref = a.reference_for_reference if sid == a.reference else a.reference
        stages = [
            ("votes", models_wonder.main, ["--strip", sid, "--top", "10", "--votes", "3", "--reference-strip", ref]),
            ("sam", models_sam.main, ["--strip", sid, "--top", "20"]),
            ("review", models_review.main, ["--strip", sid, "--top", "20"]),
        ]
        for name, fn, args in stages:
            if (out / f"{name}_{sid}.json").exists():
                print(f"{sid} {name}: done, skipped")
                continue
            print(f"{sid} {name}: running", flush=True)
            rc = fn(common + args)
            if rc != 0:
                print(f"{sid} {name}: exit {rc}", file=sys.stderr)
                return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
