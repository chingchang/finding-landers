# Report: contact sheets and suggestions for the answer key (2026-10-28)

Item 2 of the four. From the baseline v1 lists (commit 3c59e16, `out/baseline_v1/candidates_baseline_v1.json`):
for every piece of every tuning site and every strip the sites file names, the top 50 candidates within
1.5 km of the piece's refined position (the site's published position when the piece has none), as a sheet
of 50 full-resolution thumbnails and as `suggestions.json` / `suggestions.md` with PDS line and sample.
Nothing here writes to `controls/`; a person picks and copies.

## What was produced

`out/baseline_v1/sheets/`: 61 sheets (177 MB) and the two suggestion files, built in 16 min 20 s by
`scripts/contact_sheets.py`. Every piece-strip pair had at least 50 candidates in its circle; the baseline
lists are long enough that the circle is never empty. Each thumbnail is 24 m across at full resolution with
the candidate at the cross, labelled with rank, branch, calibrated score, distance from the anchor, and
line/sample.

Top candidate per piece and strip, from `suggestions.json` (score is calibrated; distance from the anchor):

| site | piece | strip | top candidate |
|---|---|---|---|
| schiaparelli | heat_shield | second date | sheet 7.01 at 89 m |
| schiaparelli | crash_scar, backshell | first date | sheet 6.43 at 334 m |
| schiaparelli | parachute | first date | sheet 6.43 at 1085 m |
| curiosity | all five pieces | | the same sheet 5.59, 138 m from the parachute anchor |
| phoenix | lander, backshell, heat_shield | first date | dark -0.34 (91 to 404 m) |
| viking1 | lander | | dark 0.18 at 934 m |
| spirit | lander | | sheet 2.67 at 901 m |
| pathfinder | lander | | shadow -0.68 at 1400 m |

(Strips are named by site and date order here; the suggestion files key them by id.)

## What the sheets show

- **The sheet branch is finding craters.** On the Schiaparelli heat-shield sheet for the second date, 47 of
  the 50 are sheet candidates and nearly all of them sit on the sunlit inner wall of a 10 to 30 m crater: a
  bright, flat crescent at exactly the scale the branch looks for, with the dark bowl beside it. The
  calibration cannot fix this; it was fitted on ground with fewer craters, so here these score as rare. The
  branch needs a crater test: a bright sheet with a dark patch of similar size adjacent on the sun side is a
  crater, a parachute has no bowl. That is a physical rule, not a shape learned from the injector, and the
  key will say what it costs in real parachutes.
- **Where the sheet branch is quiet, dark branches lead** (Phoenix, Viking 1), with calibrated scores near
  zero, which means ordinary ground; the pieces there, if present in the top 50, are not at the top.
- The pieces that share an anchor (Schiaparelli crash scar and backshell, Curiosity's five, Pathfinder's
  three without a refined position) share a sheet; the names on the sheets say which anchor was used.

## For the person filling the key

Start from `out/grids/<site>/<piece>/` (item 0) and these sheets together: the grid shows the ground, the
sheet shows what the detector ranks. Record line and sample from either into `controls/tuning.json`. A
piece absent from a sheet is information too: it is a miss at this baseline, to be scored as one.
