# The pipeline: layout and commands

```
landers/        the package: label.py (PDS3 labels), geo.py (lat/lon <-> pixel), strip.py (windowed JP2 reads,
                tiles, valid mask), detect.py (physical tests), inject.py (synthetic objects in real tiles),
                score.py (the number, and recall at a fixed false-alarm rate)
scripts/        crop_site.py, detect.py, inject.py, score.py, leakcheck.sh
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
uv run scripts/detect.py --site viking1 --run try1 [--max-tiles N]
uv run scripts/score.py out/candidates_try1.json # needs controls/thresholds.json and a filled tuning.json
uv run scripts/inject.py --site viking1 --site curiosity --tiles 6 --per-kind 3 --run inj1
                                                 # recall by size and branch at the thresholds' false-alarm rate
uv run scripts/inject.py ... --tile-phase 0 --run fit   # then:
uv run scripts/calibrate.py out/inject_fit.json --version v1 --out landers/calibration_v1.json
uv run scripts/inject.py ... --tile-phase 1 --calibration landers/calibration_v1.json --run eval
                                                 # fit on one tile set, measure on the other
```

Branches: `bright` (1 to 10 m), `shadow` (bright with a shadow of the right length), `sheet` (8 to 25 m,
flat, at 1 m/px), `dark_compact` (1 to 4 m, compact; stretched along the shadow direction scores higher),
`dark` (2.5 to 50 m).

Scores: each branch's raw score is on its own scale, so the detector maps them through
`landers/calibration_v0.json` to one scale, minus log10 of that branch's false-alarm rate per km2 at that raw
score on real tuning ground (`landers/calibrate.py`). A calibration is fitted only from uncalibrated
injection runs, and never on the tiles it is then measured on.

Pixel conventions: the package uses 0-based numpy (row, col) of pixel centres; `controls/*.json` and the crop
grid use PDS line and sample (1-based). `row = line - 1`.

Sun geometry: `SUB_SOLAR_AZIMUTH` is clockwise from image-right with down = 90 degrees; shadows fall the
opposite way. Checked on real ground by `tests/test_detect.py::test_label_shadow_direction_agrees_with_real_ground`.
