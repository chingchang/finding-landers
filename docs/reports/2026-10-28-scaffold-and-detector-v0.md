# Report: scaffold, data layer, scoring harness, detector v0 (2026-10-28)

## What I did

- Read the brief, README, docs/data.md, controls/sites.json and controls/tuning.json, the download scripts,
  the manifest and a sample of labels. Did not read controls/heldout.json.
- Built the package (`landers/`), tests, scripts and docs listed in docs/pipeline.md: 24 tests pass, ruff is
  clean, `scripts/leakcheck.sh` is clean.
- Started the download of the two summer-season Phoenix strips named in docs/data.md with the project's
  own `HiRISE/fetch_one.sh` into `HiRISE/strips/control_phoenix/`. Their manifest lines are now in
  `HiRISE/manifest.txt`.

## What I decided, and why

- **Sphere radius from MAP_RESOLUTION, not A_AXIS_RADIUS.** For the polar stereographic strips the label's
  A_AXIS_RADIUS (3396.19 km) puts the footprint about 0.1 degrees off; the radius implied by MAP_RESOLUTION
  (3376.2 km, the polar radius) centres it. Equirectangular strips agree with their labels to 3e-5 degrees
  (about a metre) either way. Test: `tests/test_geo.py`, `tests/test_strip.py::test_overview_footprint_matches_label`.
- **Windowed reads through glymur/OpenJPEG.** The strips are single-tile JPEG 2000 with 256 px precincts and
  nine resolution levels. A 2048 px window decodes in about 2 s, a 1/16 overview of the largest strip in 2 s,
  peak memory under 1.6 GB. Tiles that the overview shows as empty are skipped.
- **Sun azimuth convention pinned on real ground.** Bright patches have a dark patch on the label's shadow side
  far more often than the opposite side: 38 vs 3 on the Viking 1 strip, 80 vs 31 on Curiosity, 25 vs 14 on an
  MPL strip (output of `detect.shadow_direction_evidence`, run on the centre 2048 px window of each).
- **Scoring before detecting.** `scripts/score.py` refuses to run without `controls/thresholds.json`, which a
  person creates; my proposed values are in docs/proposals/thresholds-v0.md. The held-out key is read only with
  `--heldout` and only if the run's detector config says `"frozen": true`.
- **Detector v0 is three physical branches, no model, no persistence yet.** Bright anomaly, dark disturbance,
  and shadow pairing with length bounds from the label's incidence angle. Its grades are at most
  "needs second look", because "candidate" needs a second date.

## Numbers

From `out/candidates_viking_probe.json` (command: `uv run scripts/detect.py --site viking1 --run viking_probe --max-tiles 10`):

| what | value |
|---|---|
| tiles run | 10 (about 2.62 km2) |
| wall time | 29 s, so about 3 s per 2048 px tile |
| candidates | 45 (43 bright, 2 shadow), about 17 per km2 |

At that rate a full Viking 1 strip takes about 20 minutes and an MPL strip about 50 minutes; 34 MPL strips is
over a day on this machine. 17 per km2 is far above the proposed 2 per km2. Both are what tuning is for and
neither can start until the answer key is filled.

## What I would do next

1. A person fills `controls/tuning.json` using `scripts/crop_site.py` (1 km crop first, then `--size 512
   --center LINE,SAMPLE`), and creates `controls/thresholds.json`.
2. Run the detector over the six tuning sites, score, and tune the z thresholds, size bounds and shadow gate
   against recall@20 and false alarms per km2. Log misses in docs/experiments.md.
3. Add the persistence branch: local registration (phase correlation on a window) between two dates, which is
   the only way to the "candidate" grade and the strongest false-alarm filter on the MPL strips.
4. Speed: decode at full resolution only where the overview or a half-resolution z-map shows an anomaly, and
   run three tiles in parallel (8 GB of memory allows about three workers).
5. The model layer, once a Meta Model API key is in the environment.
