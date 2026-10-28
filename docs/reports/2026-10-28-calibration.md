# Report: one score scale for every branch (2026-10-28)

## What I did

- `landers/calibrate.py`: for each branch, the false-alarm rate per km2 as a function of raw score,
  measured on injection runs over tuning strips (a false alarm is a detection that matches no injected
  object). The calibrated score is minus log10 of that rate; above the highest false alarm seen the curve
  is extrapolated linearly in log-rate from the slope of its top decile (at least 0.15 per unit of raw
  score), and a tiny raw-score term keeps the ranking below the lowest. At most 200 knots per branch, the
  top 20 exact, so the file stays at 22 KB. A fit refuses runs that were themselves calibrated.
- `scripts/calibrate.py` fits from `scripts/inject.py` outputs, which now carry the raw detections and
  truths and a `--tile-phase` (two interleaved tile sets), so a scale fitted on phase 0 is measured on
  phase 1. `scripts/detect.py` applies `landers/calibration_v0.json` by default (`--no-calibration` for raw).
- Fitted `landers/calibration_v0.json` on phase 0 (`out/inject_fit_p0.json`: viking1, curiosity, spirit,
  pathfinder, 19 tiles, 8.487 km2, seed 0). Measured on phase 1 (seed 1, 8.126 km2) raw and calibrated.

Green: 35 tests, ruff clean, leak check clean over 41 files.

## Numbers

False alarms per branch on the fitting ground, from `out/inject_fit_p0.json` through `scripts/calibrate.py`:

| branch | false alarms | per km2 | raw score range of false alarms |
|---|---|---|---|
| bright | 1260 | 148 | 4.09 to 26.28 |
| dark_compact | 1607 | 189 | 4.05 to 13.26 |
| dark | 561 | 66 | 1.85 to 6.63 |
| sheet | 537 | 63 | 3.06 to 5.42 |
| shadow | 127 | 15 | 6.39 to 20.79 |

Recall at the thresholds' 2.0 false alarms per km2 on the phase 1 tiles, which the calibration never saw:

| | raw scores (`out/inject_eval_p1_raw.json`) | calibrated (`out/inject_eval_p1_cal.json`) |
|---|---|---|
| score threshold | 13.813 | 0.873 |
| detections kept | 27 (16 false, 1.969/km2) | 46 (16 false, 1.969/km2) |
| recall overall | 0.064 | 0.158 |
| sheet 8-12 m | 0 of 13 | 3 of 13 |
| sheet 12-18 m | 0 of 20 | 5 of 20 |
| sheet 18-25 m | 0 of 24 | 9 of 24 |
| blob_shadow 1-2 m | 3 of 17 | 2 of 17 |
| blob_shadow 2-3 m | 6 of 17 | 3 of 17 |
| blob_shadow 3-5 m | 0 of 23 | 2 of 23 |
| dark_compact 1-2 m | 1 of 18 | 2 of 18 |
| dark_compact 2-3 m | 1 of 22 | 1 of 22 |
| dark_compact 3-4 m | 0 of 17 | 0 of 17 |

## What I decided, and why

- **Calibrate on false alarms, not on hits.** The rate of false alarms at a score is a property of the
  ground, measurable without an answer key and without assuming what hardware looks like. A calibration
  built on hits would bake the injected contrasts into the detector.
- **Fit and measure on different tiles.** The phase 1 numbers are the ones to quote; a number measured on
  the fitting tiles would be optimistic.
- **The gain is where expected and no further.** The common scale lets the sheet branch, whose false
  alarms are rare, into the kept set: sheets go from none to 17 of 57 at 2 per km2. Small bright and dark
  objects are still confused with rocks at every score, so calibration cannot help them; shape and
  persistence can. Overall recall 0.064 to 0.158 is a real gain and still far from the pass line of 0.8.
- **Calibrated scores are not comparable across calibrations.** A run's detector config records the
  calibration file, and the score script's `--heldout` requires a frozen config, so a frozen detector
  freezes its calibration with it.

## What I would do next

1. Shape features for `bright` and `dark_compact`: rocks have a shadow-side gradient and a compact
   bright-dark pair; a lander platform is wider than tall. Edge sharpness and the bright-to-shadow ratio
   should separate them better than peak z.
2. Persistence between two dates, the route to the "candidate" grade; it removes rocks only if
   registration is good enough that a rock in both dates is not counted as persistent, so it must be
   tested with injection too (inject on one date only).
3. Fill the answer key and run the real pieces; a sheet recall of 0.3 at modest contrast says parachutes
   near saturation should do better, and only the real ones can say by how much.
