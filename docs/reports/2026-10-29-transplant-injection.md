# Report: transplant injection, real pieces planted into search-area ground (2026-10-29)

Plan item 7, branch `claude/transplant`. Every number below is copied from
`out/transplant_t1/transplant_t1.json`, written by `scripts/transplant.py --run t1 --copies 6 --nearest 4
--tiles-per-strip 6 --seed 0` at this commit with detector v0.1 and `landers/calibration_v0.json`
(`out/` is not committed; the command rebuilds the file in about five minutes). The tables were printed from
that file by `experiments/transplant_summary.py`. The two sheets beside it, `cuts.png` and `placements.png`,
show every cut at its source and every planting, for checking by eye.

## What was built

`landers/transplant.py`, `scripts/transplant.py`, `tests/test_transplant.py`; `landers/score.py` gained a
per-truth match radius and a grouping argument on the injection scorer, nothing else changed.

- **The cut.** For each of the 18 recorded pieces in `controls/tuning.json`, a disc of its strip at full
  resolution around the recorded line and sample, with radius half the piece's size plus the shadow of a 3 m
  object under the source sun plus 2.5 m for the key's own precision (30 to 65 px at 25 cm, 18 to 27 px at
  50 cm). The disc is stored as a gain: each pixel over the median of a 24 px ring of ground outside it, so
  the object stays as many times brighter or darker than its surroundings as at home. Saturated pixels are
  flagged and stay saturated when planted. The rim is feathered with a 3 px Gaussian.
- **The target.** Search-area strips only (manifest case `mpl_summer`, control strips excluded by code) of
  the same map scale, the four whose tangent of incidence is nearest the source's. Six tiles per target strip,
  spread along the footprint, each 2048 px. The cut is rotated so the source's shadow direction becomes the
  target's (both from the labels' sub-solar azimuth; the rotation is pinned by a test), planted at random
  fully valid spots that do not overlap, and the ratio of target to source tangent is recorded per planting.
- **The sham control.** For every piece, a second cut of the same radius from plain ground 120 m away on the
  same strip, at least 50 m from every recorded piece, planted the same way. If shams are detected, the seam
  is being detected. Sham detections count as false alarms.
- **The score.** The same detector pass as a real run (calibrated, candidates below score -3 dropped), then
  `recall_at_false_alarm_rate`: the score threshold that keeps false alarms at 2 per km2 over the planted
  tiles (from `controls/thresholds.json`), recall at that threshold by piece, by kind and by site, with the
  thresholds' match radius per kind (5 m; 20 m for marks). Per planting the file also records the best
  detection within the radius at any score and its rank in its tile.
- **Rules in code.** A source must be a tuning strip (a recorded piece on any other strip raises); a target
  must be a search strip; held-out, spare and final-exam strips cannot be cut from or planted into.

Green: 121 tests, ruff clean over the package, leak check clean over 108 files.

## The run

46 tiles, 16.520 km2, 290 s. 18 cuts and 18 shams, 108 real plantings and 108 sham plantings. Targets, with
incidence and the sources that went there:

| target | incidence | tan | sources planted (tan ratio target over source) |
|---|---|---|---|
| ESP_048734_1035, ESP_013368_1035, PSP_004336_1035, PSP_004402_1030 | 56.79 to 57.37 | 1.528 to 1.562 | Schiaparelli, Curiosity, Phoenix, Viking 1 (1.266 to 1.329) |
| ESP_013078_1030, ESP_013500_1035, ESP_013724_1030, PSP_004824_1030 | 57.78 to 58.50 | 1.587 to 1.632 | Spirit (0.981 to 1.009) |
| ESP_057965_1035 (50 cm) | 59.32 | 1.686 | Pathfinder (1.02) |

Four of the six sources have the sun at about 50 degrees (tan 1.18 to 1.21) and no search strip is lower than
56.79 degrees, so their planted shadows are 27 to 33 percent shorter than a native object's would be. The
detector's shadow test admits heights from 0.5 to 3 m, so a 2 m object still passes; the ratio is on every
planting for anyone who wants to exclude them.

## The score

False alarms allowed 33 over 16.520 km2; score threshold 0.169; 57 detections kept, 33 false (1.998 per km2).

| kind | plantings | found | recall | branches |
|---|---|---|---|---|
| hardware | 72 | 16 | 0.222 | bright 10, sheet 4, shadow 2 |
| fabric | 24 | 6 | 0.250 | sheet 6 |
| mark | 12 | 0 | 0.000 | |
| all | 108 | 22 | 0.204 | |

Per piece (six plantings each): found at the threshold, plantings with any detection within the radius at
any score, the median calibrated score of those, and their ranks within their tiles.

| site / piece | found | any detection | median best score | ranks in tile |
|---|---|---|---|---|
| schiaparelli / crash_scar | 0 | 1 | -1.69 | 104 |
| schiaparelli / parachute | 2 | 5 | -0.07 | 1, 1, 1, 2, 3 |
| schiaparelli / backshell | 2 | 2 | 4.53 | 1, 2 |
| schiaparelli / heat_shield | 0 | 2 | -2.09 | 99, 172 |
| curiosity / parachute | 2 | 5 | -0.62 | 1, 1, 2, 6, 21 |
| curiosity / backshell | 3 | 6 | 0.17 | 1, 1, 1, 5, 53, 55 |
| curiosity / heat_shield | 0 | 5 | -0.99 | 1, 1, 4, 31, 103 |
| curiosity / descent_stage | 0 | 2 | -1.65 | 74, 143 |
| phoenix / lander | 1 | 5 | -0.66 | 1, 2, 3, 4, 6 |
| phoenix / backshell | 0 | 5 | -0.45 | 1, 1, 2, 2, 2 |
| phoenix / heat_shield | 0 | 4 | -1.27 | 3, 7, 30, 114 |
| viking1 / lander | 3 | 6 | -0.27 | 1, 2, 3, 16, 31, 67 |
| spirit / lander | 0 | 4 | -0.81 | 2, 3, 3, 132 |
| spirit / parachute | 2 | 5 | 0.04 | 1, 1, 1, 7, 12 |
| spirit / backshell | 4 | 6 | 0.37 | 1, 1, 1, 1, 2, 162 |
| pathfinder / lander | 0 | 1 | -1.64 | 488 |
| pathfinder / backshell | 3 | 5 | 0.74 | 1, 1, 1, 1, 45 |
| pathfinder / parachute | 0 | 1 | -1.57 | 204 |

70 of the 108 real plantings have a detection within their match radius at some score; 22 pass the threshold.

Per target strip, the ground matters more than the piece:

| target | real plantings | found | any detection | detections in its 6 tiles | kept above threshold |
|---|---|---|---|---|---|
| PSP_004402_1030 | 22 | 7 | 11 | 22 | 10 |
| PSP_004336_1035 | 13 | 4 | 10 | 31 | 5 |
| ESP_013368_1035 | 20 | 1 | 13 | 1208 | 2 |
| ESP_048734_1035 | 17 | 1 | 14 | 960 | 3 |
| ESP_013078_1030 | 3 | 1 | 2 | 1791 | 23 |
| ESP_013500_1035 | 9 | 3 | 8 | 777 | 3 |
| ESP_013724_1030 | 4 | 2 | 3 | 410 | 2 |
| PSP_004824_1030 | 2 | 0 | 2 | 750 | 0 |
| ESP_057965_1035 | 18 | 3 | 7 | 2170 | 10 |

## The sham control

1 of 108 sham plantings has a kept detection within its radius (rate 0.009); 13 of 108 have a detection at
any score. The one kept is the Viking 1 lander's sham on PSP_004336_1035: branch `sheet`, score 3.01, rank 1
in its tile, 8.2 px from the planting centre. Three more shams carry a `sheet` detection at ranks 2 to 5
below the threshold (Curiosity's backshell and parachute shams, Phoenix's backshell sham). So the seam is
not invisible: on the smoothest search ground a disc whose mean gain is not exactly one reads as a faint
bright sheet. Hardware or fabric hits found by `sheet` alone (4 of the 16 hardware hits, 1 Phoenix lander,
1 Curiosity backshell, 2 Schiaparelli backshell) should be read with that in mind; the Schiaparelli backshell
cut also holds the edge of the saturated canopy, recorded in the file under `other_pieces_in_cut`, so its
`sheet` hits are the canopy, not the seam.

## What it says

- **Detection is not the gap; ranking is.** Two thirds of the plantings are detected, one fifth survive the
  false-alarm budget. The same conclusion as the calibration and persistence reports, now on real hardware
  in real search ground.
- **The ground sets the threshold.** The two 2007 strips PSP_004336_1035 and PSP_004402_1030 yield 2 to 10
  calibrated detections per tile; ESP_013078_1030 yields about 300. One threshold over all of them is what
  the search will apply, so this is the honest number, but it means recall on the quiet strips (11 of 35
  found) is three times that on the busy ones, and that the calibration fitted on equatorial ground does not
  put polar false alarms at 2 per km2.
- **Dust-covered dark hardware is lost.** Phoenix's three pieces, dark spots on that date, are found 1 of
  18 times; they are detected at ranks 1 to 6 by the `dark` branch and then outscored. Marks (12 plantings)
  are never found. The Pathfinder lander at 50 cm is found 0 of 6 and detected once.
- **Bright compact pieces with shadows do best**: Spirit's backshell 4 of 6, Viking 1's lander and the
  Curiosity and Pathfinder backshells 3 of 6.

## What I decided, and why

- **Gain, not pixels.** Pasting pixels would carry each source's exposure; dividing by the ring median keeps
  the physical quantity, the object's contrast against its own ground, and lets the target's exposure and
  ground brightness through. The synthetic injector works the same way, so the two scores are comparable.
- **Rotation to the target's shadow direction, no stretch for incidence.** Stretching the shadow would also
  stretch the object. The tangent ratio is recorded instead, and the four targets nearest in incidence were
  chosen so the ratio is as close to one as the data allow.
- **Shams count as false alarms**, which makes the threshold stricter, not looser, when the seam is seen.
- **The planting ground is the search area**, as item 7 specifies (docs/design.md says the same). The rule
  "never tune on the search area" is about tuning toward an answer there; no answer is used, only the ground's
  false alarms. The 46 tiles are listed in the results file under `targets.tiles` so a person can confirm
  this reading or substitute other polar ground; I flag it rather than decide it.
- **One global threshold across targets**, because the search will use one.

## What I would do next

1. Fit a plane to the ring instead of a constant, or normalise the disc's weighted mean gain to the ring's,
   and rerun; the sham `sheet` hits should vanish. Cheap, and it removes the one caveat on the sheet numbers.
2. Item 8 should score each change with `scripts/transplant.py --run <name> --seed 0` and compare
   `score_by_kind` to t1's 0.222 / 0.250 / 0.000; a second seed for anything that looks like a gain.
3. A calibration fitted on polar false alarms (shams and empty tiles of these same targets) so that the
   common scale means the same thing on the search ground; measured on a different tile set.
4. The `dark` branch finds dust-covered hardware at rank 1 to 6 in the tile; a shape or persistence feature
   that lifts those above polygon troughs is the route to Phoenix-like pieces.
