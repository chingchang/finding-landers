# Report: sheet and dark-compact branches, injection score, leak-check allowlist, crop grid (2026-10-28)

## What I did

- Merged main into this branch (brief, docs, controls, manifest). `controls/thresholds.json` and the two
  Phoenix manifest lines were in the main working tree but not committed there; I copied them in verbatim
  and committed them here. Commit your copies on main before merging this branch, or git will refuse to
  overwrite the modified manifest.
- `sheet` branch: bright, flat patches 8 to 25 m across, found at 1 m/px (4x block mean) with a 65/31 px
  annulus, z > 3, flatness (mean z / peak z) >= 0.45, extent <= 35 m. No shadow required.
- `dark_compact` branch: dark patches 1 to 4 m across, z < -4, area / bounding box >= 0.45. A shadow is
  optional: when the patch's long axis lies along the shadow direction the score is raised by 1.3.
- Injection (`landers/inject.py`, `scripts/inject.py`): sheets (+35% of local background, aspect 0.5),
  dark compacts (-35%, half of them with a shadow) and blob-plus-shadow objects (+50%, shadow -50%) of
  known size drawn into real tiles of tuning or spare strips only. `score.recall_at_false_alarm_rate`
  finds the score threshold that keeps unmatched detections at the thresholds' rate and reports recall by
  kind, size bin and branch. The search area and sealed sites are refused.
- Leak check now scans every file git tracks or would track, except the allowlist `docs/data.md`,
  `controls/`, `HiRISE/manifest.txt`. Tests build their one fake id at runtime so the source never holds
  the pattern; the tests that need real strips take ids from the manifest and sites file.
- `crop_site.py --grid`: full-resolution 512 px tiles covering 1.5 km around a position, numbered row-major
  with an index image, each tile labelled with its PDS line and sample range. 144 tiles in 9 s for Viking 1.
- Scorer: `match_radius_m` from the thresholds file is converted per strip through MAP_SCALE; detector
  output now records `scale_m`.

Green: 30 tests, ruff clean, leak check clean over 36 files.

## Numbers

All from `scripts/inject.py` with seed 0, detector v0.1, 3 objects per kind per tile.

`out/inject_inj_v01_4sites.json` (viking1, curiosity, spirit, pathfinder; 6 tiles each; 5.408 km2;
false-alarm target 2.0/km2 from controls/thresholds.json):

| | value |
|---|---|
| false alarms allowed | 10 |
| score threshold that keeps them | 13.498 |
| detections kept | 16 (10 false, 1.849/km2) |
| recall overall | 0.048 |

| kind | size | n | found | branches |
|---|---|---|---|---|
| blob_shadow | 1-2 m | 11 | 2 | shadow |
| blob_shadow | 2-3 m | 6 | 1 | shadow |
| blob_shadow | 3-5 m | 25 | 1 | shadow |
| dark_compact | 1-2 m | 14 | 2 | dark_compact |
| dark_compact | 2-3 m | 13 | 0 | |
| dark_compact | 3-4 m | 15 | 0 | |
| sheet | 8-12 m | 13 | 0 | |
| sheet | 12-18 m | 14 | 0 | |
| sheet | 18-25 m | 15 | 0 | |

`out/inject_inj_v01_4sites_fa20.json` (same tiles, target 20/km2): threshold 8.007, 139 kept, 108 false,
recall overall 0.214.

`out/inject_inj_v01_nolimit.json` (viking1 and curiosity, 4 tiles each, 0.742 km2, no false-alarm limit):
recall overall 0.889; every kind is found by its intended branch (sheets by `sheet` 8 of 9, dark compacts
by `dark_compact` 6 of 9, blobs by `shadow` 5 of 9 and `bright` 2 of 9).

## What I decided, and why

- **The branches work; the ranking does not yet.** With no alarm budget the injected objects are recovered
  and land in the right branch. At the thresholds' 2 per km2 almost nothing survives, because ordinary
  bright rocks reach peak z of 8 to 13 on this ground and the branch scores are not on one scale: `sheet`
  scores a mean z of 3 to 5, `shadow` a peak z times 1.5, so a single threshold keeps only `shadow`. The
  injection harness is the tool to fix this, and it needed to exist before the fix.
- **Injected contrasts are modest on purpose** (+35% sheet, +50% blob). Real parachutes and landers are
  often brighter than anything natural in the strip, up to saturation, so these numbers are a floor, not an
  estimate of recall on real hardware.
- **Grid first, then zoom.** On the Viking 1 index image the published position falls at the corner of
  tiles 78, 79, 90 and 91. Tile 79 holds a small bright patch with a dark patch on its shadow side near its
  upper left (about line 40528, sample 14707). Whether that is the lander is for you to decide when filling
  `controls/tuning.json`; the detector has not been run against it and nothing here is a claim.

## What I would do next

1. Put every branch's score on one scale: the false-alarm rate of that score on real tuning ground
   (a per-branch percentile from the injection runs), so the threshold means the same thing in each branch.
2. Raise the sheet and dark-compact scores with shape: elongation and edge sharpness separate sheets from
   bright slopes, and compact fill from crater shadows.
3. Persistence between dates, which is the planned route to the "candidate" grade and the strongest filter.
4. Fill the answer key with the grid tool and score the real pieces.
