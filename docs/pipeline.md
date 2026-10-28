# The pipeline: layout and commands

```
landers/        the package: label.py (PDS3 labels), geo.py (lat/lon <-> pixel), strip.py (windowed JP2 reads,
                tiles, valid mask), detect.py (physical tests), score.py (the number)
scripts/        crop_site.py, detect.py, score.py, leakcheck.sh
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
uv run pytest                                    # 24 tests, about 8 s with the strips on disk
scripts/leakcheck.sh                             # no image ids or sealed-site coordinates in code or results
uv run scripts/crop_site.py viking1              # 1 km crop at the published position, PDS line/sample grid
uv run scripts/crop_site.py viking1 --size 512 --center LINE,SAMPLE
uv run scripts/detect.py --site viking1 --run try1 [--max-tiles N]
uv run scripts/score.py out/candidates_try1.json # needs controls/thresholds.json and a filled tuning.json
```

Pixel conventions: the package uses 0-based numpy (row, col) of pixel centres; `controls/*.json` and the crop
grid use PDS line and sample (1-based). `row = line - 1`.

Sun geometry: `SUB_SOLAR_AZIMUTH` is clockwise from image-right with down = 90 degrees; shadows fall the
opposite way. Checked on real ground by `tests/test_detect.py::test_label_shadow_direction_agrees_with_real_ground`.
