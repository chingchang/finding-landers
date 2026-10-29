# Report: contact sheets, second pass (2026-10-28)

Plan item 2b, by the unattended loop. The sheets were rebuilt from the baseline v1 lists
(`out/baseline_v1/candidates_baseline_v1.json`, commit 3c59e16) without touching them, into
`out/baseline_v1/sheets_v2/` (92 files, 248 MB, log in `out/baseline_v1/sheets_v2.log`). The first-pass sheets
under `out/baseline_v1/sheets/` are left as they were, because the nine key entries a person has already filled
came from them. Reports may now name strips, so this one does.

## What I did

- **One stretch per sheet.** `landers/sheets.py` reads the raw crops of every thumbnail of a piece and strip
  (both sheets, see below), takes one pair of 0.5 and 99.5 percentiles over all their valid pixels, and
  applies it to every thumbnail. The limits are printed in the sheet footer and recorded as `stretch_dn` in
  `suggestions.json`. The `cut_grids.py` tiles were already cut from one stretched window per grid, so nothing
  changed there and the grids were not rebuilt.
- **A second ranking: the two-sided shadow test.** For every candidate within the search radius (not only the
  top 50 by score), on a 128 px full-resolution crop: the object disc (radius from the candidate's own area,
  clamped to 2 to 16 px), a probe from the disc's edge along the label's shadow direction out to the shadow of
  a 3 m object (`SUB_SOLAR_AZIMUTH`, `INCIDENCE_ANGLE`; the same convention as the detector, which
  `tests/test_detect.py` pins on real ground), the mirror probe on the sun side, and an annulus of ground
  outside both for the local mean and standard deviation. Each probe is averaged per 1 px step, smoothed over
  3 steps, and its darkest stretch taken; the same operation on both sides, so noise biases both alike. The
  score is `min(z_centre, -z_anti) + min(0, z_sun)`: a bright blob with a dark anti-sun side scores high; dark
  on the sun side, which is what a trough, a polygon edge or a crater's shadowed wall shows beside its bright
  far wall, costs; dark on both sides earns nothing. On the Viking 1 strip, bright candidates are darker on the
  anti-sun side than on the sun side 3 times in 4 (`tests/test_sheets.py`, pinned at 60 percent), which fixes
  the sign.
- **Two sheets and one map per piece and strip.** `<site>_<piece>_<strip>.png` holds the top 50 by score,
  `..._shadow.png` the top 50 by shadow score; every cell carries both ranks (`#` by score, `S` by shadow),
  the shadow score, and line and sample; the footer carries an arrow the way shadows fall. The map draws the
  score picks in yellow and the shadow picks in magenta. `suggestions.json` lists both sets with the three z
  values per pick; `suggestions.md` prints both top-10 tables.
- **Schiaparelli: 3 km around each strip's own centre.** `--strip-centre schiaparelli --radius-for
  schiaparelli=3000` anchors every piece at the centroid of the strip's valid footprint. The
  `cut_grids.py` tile numbers still refer to the grid around the refined position, which the map draws, so a
  pick can still be found on the existing tiles. A consequence: the four Schiaparelli pieces share one anchor
  per strip and so one sheet pair; the four copies are identical.
- **Leak check.** `scripts/leakcheck.sh` no longer flags observation ids under `docs/reports/`; the sealed-site
  name and coordinate rules apply there as everywhere. `tests/test_leakcheck.py` checks all three cases.
- Tests: 57 green with the strips on disk (`LANDERS_DATA`), 43 green and 14 skipped without; ruff clean; leak
  check clean over 65 files.

Rebuild command; the shadow passes took 13 to 103 s per strip (`sheets_v2.log`), one 2048 px block in memory
at a time:

    uv run scripts/contact_sheets.py out/baseline_v1/candidates_baseline_v1.json --out out/baseline_v1/sheets_v2 \
        --strip-centre schiaparelli --radius-for schiaparelli=3000

## Numbers

From `out/baseline_v1/sheets_v2/suggestions.json` (table by `experiments/suggestions_table_v2.py`). "within":
candidates in the search area, all of them shadow-tested; "by score" and "by shadow": branch mix of each top
50 and the top value; "best": the top shadow pick's score, its rank by detector score, and its distance from
the anchor; "both": how many of the 50 appear in both lists. Pieces that share an anchor share a row.

| site | piece | strip | within | by score: branches, top | by shadow: branches, best (#, dist) | both | stretch DN |
|---|---|---|---|---|---|---|---|
| schiaparelli | all four | ESP_048041_1780 | 51135 | sheet 50, 7.95 | bright 36 sheet 14, +2.7 (#36049, 2796 m) | 0 | 370..596 |
| schiaparelli | all four | ESP_073625_1780 | 65194 | sheet 50, 8.40 | bright 37 sheet 10 shadow 3, +4.1 (#18226, 2972 m) | 0 | 212..734 |
| curiosity | parachute | ESP_030313_1755 | 4512 | dark 30 dark_compact 18 sheet 1 bright 1, 5.59 | shadow 29 bright 17 sheet 4, +5.9 (#167, 1180 m) | 0 | 270..575 |
| curiosity | backshell, rover | ESP_030313_1755 | 5133 / 5131 | dark 30 dark_compact 18 sheet 1 bright 1, 5.59 | shadow 28 bright 18 sheet 4, +5.9 (#176, 1372 m) | 0 | 319..582 |
| curiosity | heat_shield | ESP_030313_1755 | 3550 | dark 14 dark_compact 13 bright 12 sheet 10 shadow 1, 5.59 | shadow 24 bright 23 sheet 3, +5.9 (#161, 722 m) | 1 | 77..530 |
| curiosity | descent_stage | ESP_030313_1755 | 5441 | dark 39 dark_compact 10 sheet 1, 5.59 | shadow 25 bright 18 sheet 7, +5.3 (#689, 1271 m) | 0 | 396..605 |
| phoenix | lander | ESP_017716_2485 | 1152 | dark 23 dark_compact 21 sheet 5 shadow 1, -0.34 | bright 45 shadow 3 sheet 2, +5.2 (#68, 405 m) | 2 | 78..211 |
| phoenix | lander | ESP_053451_2485 | 7223 | dark 36 dark_compact 13 bright 1, 0.28 | sheet 39 bright 11, +1.3 (#4904, 815 m) | 0 | 82..223 |
| phoenix | backshell | ESP_017716_2485 | 1131 | dark 24 dark_compact 20 sheet 4 shadow 2, -0.34 | bright 46 shadow 2 sheet 2, +5.2 (#64, 91 m) | 3 | 76..211 |
| phoenix | backshell | ESP_053451_2485 | 7060 | dark 34 dark_compact 14 sheet 1 bright 1, 0.16 | sheet 38 bright 12, +2.8 (#3996, 1341 m) | 1 | 80..222 |
| phoenix | parachute | ESP_017716_2485 | 1149 | dark 22 dark_compact 20 sheet 5 shadow 3, -0.34 | bright 45 shadow 3 sheet 2, +5.2 (#66, 477 m) | 4 | 78..211 |
| phoenix | parachute | ESP_053451_2485 | 7237 | dark 36 dark_compact 13 bright 1, 0.28 | sheet 39 bright 11, +1.3 (#4933, 867 m) | 0 | 83..224 |
| phoenix | heat_shield | ESP_017716_2485 | 1176 | dark 24 dark_compact 22 sheet 3 shadow 1, -0.34 | bright 45 shadow 3 sheet 2, +5.2 (#71, 311 m) | 2 | 77..211 |
| phoenix | heat_shield | ESP_053451_2485 | 7213 | dark 35 dark_compact 13 sheet 1 bright 1, 0.28 | sheet 38 bright 12, +1.3 (#4873, 794 m) | 1 | 82..223 |
| viking1 | lander | ESP_046170_2025 | 1938 | sheet 24 dark 23 dark_compact 3, 0.18 | bright 33 shadow 11 sheet 6, +6.0 (#124, 384 m) | 0 | 314..786 |
| spirit | lander | ESP_025815_1655 | 10481 | dark_compact 22 sheet 10 shadow 6 bright 6 dark 6, 2.67 | shadow 48 bright 2, +7.7 (#396, 1055 m) | 3 | 352..558 |
| spirit | parachute, backshell, heat_shield | ESP_025815_1655 | 10085 | dark_compact 21 sheet 10 shadow 7 bright 6 dark 6, 2.67 | shadow 49 bright 1, +7.7 (#387, 1151 m) | 3 | 352..558 |
| pathfinder | lander | ESP_022038_1995 | 745 | sheet 31 shadow 11 dark 8, -0.68 | bright 25 sheet 14 shadow 11, +5.0 (#9, 1438 m) | 11 | 255..823 |
| pathfinder | backshell, parachute, heat_shield | ESP_022038_1995 | 899 | shadow 21 sheet 17 dark 11 dark_compact 1, -0.13 | bright 27 shadow 19 sheet 4, +4.2 (#36, 915 m) | 19 | 244..796 |

## What it says, and what it cannot say

- **The two rankings barely overlap.** On 15 of the 30 piece-strip pairs no candidate is in both top 50s,
  and never more than 4 except at Pathfinder (11 and 19, where the score list is already shadow-led). The score ranks dark
  patches and sheets; the shadow test ranks bright blobs with a shadow. A person now sees both slices of the
  same list, which was the point.
- **On polar ground the shadow sheet is a different picture.** On the first Phoenix date the score sheet is
  dark patches with calibrated scores below zero, which means ordinary ground; the shadow sheet's top pick is a
  bright compact blob with dark pixels on its shadow side, score +5.2 against +2.9 for the next, at rank 64 by
  score and 91 m from the backshell anchor. What it is, is for the person filling the key; the sheet only says
  the detector's own ordering put it 64th.
- **Schiaparelli's 3 km area quadruples the list and the score sheet stays crater walls** (sheet 50 of 50, top
  7.95 and 8.40 against 6.43 and 7.01 at 1.5 km). The shadow sheet there is 36 bright specks at +2.7 and
  below on the first date; the ground is rough and nothing stands far above it. The 3 km circle is the right
  area for the published precision; a top 50 is a thin slice of 51135, and `within` says so.
- **The stretch now means something across a sheet.** The first Phoenix date is 76 to 211 DN over its whole
  sheet, Viking 1 is 314 to 786; a bright object on either sheet is bright against its neighbours, not against
  its own crop.
- **Nothing here changes a score or a list.** The shadow test is a sheet aid, computed on the same candidates
  the baseline produced; plan item 6 is where it would enter the score, with its threshold recorded.
- I did not look up where the nine filled key entries fall in the shadow ranking. Item 4 scores the baseline
  against the key blind; a peek now would be tuning the sheets on the answer.

## What I would do next

Item 3 is still a person's: 13 of 22 pieces are open in `controls/tuning.json`, and the shadow sheets are
built for the ones the score sheets did not show (Phoenix, Viking 1). Then item 4, the first score. The shadow
test's three z values are on every pick in `suggestions.json`, so once the key is full, item 6 can ask the
question it needs: for each real piece, where does it sit in that strip's distribution of shadow scores.
