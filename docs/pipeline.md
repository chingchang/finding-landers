# The pipeline: layout and commands

```
landers/        the package: label.py (PDS3 labels), geo.py (lat/lon <-> pixel), strip.py (windowed JP2 reads,
                tiles, valid mask), detect.py (physical tests), shape.py (shape and shadow-side features, and
                the versioned rules that put some into the score), features_eval.py (where the real pieces sit
                among false alarms; reads the key, so it is scoring-side), inject.py (synthetic objects in real
                tiles), score.py (the number, and recall at a fixed false-alarm rate)
scripts/        crop_site.py, detect.py, feature_percentiles.py, rescore.py, inject.py, score.py, leakcheck.sh
tests/          pytest; data tests skip unless LANDERS_DATA points at a directory with strips/
controls/       sites.json (published positions, groups), tuning.json (answer key, filled by a person),
                thresholds.json (pass/fail numbers, created by a person), heldout.json (sealed, gitignored)
docs/proposals/ numbers the agent proposes; a person copies them into controls/
docs/reports/   one short report per piece of work
experiments/    scratch; nothing here is a result
out/            every run's output; never committed
```

Setup: `uv sync`. Data: `export LANDERS_DATA=/path/to/HiRISE` (default `<repo>/HiRISE`).

```
uv run pytest                                    # 30 tests, about 20 s with the strips on disk
scripts/leakcheck.sh                             # scans every tracked file except docs/data.md, controls/,
                                                 # HiRISE/manifest.txt for image ids and sealed-site facts
uv run scripts/crop_site.py viking1              # 1 km crop at the published position, PDS line/sample grid
uv run scripts/crop_site.py viking1 --grid       # 144 numbered full-res 512 px tiles over 1.5 km + index.png
uv run scripts/crop_site.py viking1 --size 512 --center LINE,SAMPLE
uv run scripts/detect.py --site viking1 --run try1 [--max-tiles N] [--jobs 3]   # records the commit hash;
                                                 # the file is rewritten after every strip; --resume skips the
                                                 # strips an interrupted run of the same config already wrote;
                                                 # --no-shape-rules records features and adds nothing to the score
uv run scripts/feature_percentiles.py out/candidates_<run>.json --rules landers/shape_v1.json --out out/<run>_rules.json
                                                 # per recorded piece, the fraction of same-branch false alarms on
                                                 # its strip at or beyond each feature value; per rule, the
                                                 # false-alarm pass fraction and the gain -log10(p) it would earn
uv run scripts/rescore.py out/candidates_<run>.json landers/shape_v1.json   # the rules applied to a recorded run
uv run scripts/cut_grids.py                      # 1.5 km numbered full-res grids around every refined piece
uv run scripts/contact_sheets.py out/<run>/candidates_<run>.json      # top 50 per piece within 1.5 km, for the key:
                                                 # a thumbnail sheet and an overview map per piece per strip, both
                                                 # numbered by rank; suggestions.{json,md} with line, sample and the
                                                 # cut_grids tile number of each pick
uv run scripts/persist.py out/<run>/candidates_<run>.json --site schiaparelli [--inject-check 4]
                                                 # seen on both dates -> grade "candidate"; radius 8 px;
                                                 # --reuse-nodes <previous persist json> skips registration
uv run scripts/score.py out/candidates_try1.json # needs controls/thresholds.json and a filled tuning.json
uv run scripts/inject.py --site viking1 --site curiosity --tiles 6 --per-kind 3 --run inj1
                                                 # recall by size and branch at the thresholds' false-alarm rate
uv run scripts/inject.py ... --tile-phase 0 --run fit   # then:
uv run scripts/calibrate.py out/inject_fit.json --version v1 --out landers/calibration_v1.json
uv run scripts/inject.py ... --tile-phase 1 --calibration landers/calibration_v1.json --run eval
                                                 # fit on one tile set, measure on the other
uv run scripts/inject.py ... --features          # AUC of each shape feature, hits vs false alarms
```

Branches: `bright` (1 to 10 m), `shadow` (bright with a shadow of the right length), `sheet` (8 to 25 m,
flat, at 1 m/px), `dark_compact` (1 to 4 m, compact; stretched along the shadow direction scores higher),
`dark` (2.5 to 50 m).

Scores: each branch's raw score is on its own scale, so the detector maps them through
`landers/calibration_v0.json` to one scale, minus log10 of that branch's false-alarm rate per km2 at that raw
score on real tuning ground (`landers/calibrate.py`). A calibration is fitted only from uncalibrated
injection runs, and never on the tiles it is then measured on.

Shape rules (`landers/shape_v<n>.json`, applied by the detector after calibration): a rule names a branch set,
a physical test on recorded features (two-sided shadow contrast, shadow height, isolation, saturation) and the
fraction `p` of that branch's false alarms on the tuning strips that pass it; a passing candidate gains
`-log10(p)` on the calibrated scale, a failing one keeps its score. Thresholds are physical or round numbers,
written before the false-alarm distributions were seen; the pass fractions are measured by
`scripts/feature_percentiles.py` and copied into the file with the run they came from.

A baseline run that the key will be filled from lives under `out/baseline_v1/` with its commit hash in
`COMMIT` and in the run file, and is never rerun once the key is filled. Run it from a frozen export of the
commit (`git archive <hash> | tar -x -C <dir>`; `LANDERS_COMMIT=<hash>`), because worker processes import
the working tree.

Pixel conventions: the package uses 0-based numpy (row, col) of pixel centres; `controls/*.json` and the crop
grid use PDS line and sample (1-based). `row = line - 1`.

Sun geometry: `SUB_SOLAR_AZIMUTH` is clockwise from image-right with down = 90 degrees; shadows fall the
opposite way. Checked on real ground by `tests/test_detect.py::test_label_shadow_direction_agrees_with_real_ground`.
