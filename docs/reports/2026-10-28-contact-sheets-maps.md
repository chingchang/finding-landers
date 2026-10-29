# Report: contact sheets, part 2: overview maps, grid tile numbers, summaries (2026-10-28)

Plan item 2, done by the unattended plan loop while an interactive session was doing the same item in
the same worktree. That session's report is `2026-10-28-contact-sheets.md` (what the top picks are and
what the sheets show); this one covers what the loop session added to the tool and the rerun it made.
The picks are the same in both: the selection code did not change, only what is written around it.

## What I did

- `scripts/contact_sheets.py` now writes, per piece and strip, an overview map beside the thumbnail sheet:
  the whole 1.5 km circle at 2 m/px (decoded from the JPEG 2000 resolution levels through the new
  `Strip.read_reduced`, about 10 s each, no 300 MB read), with every pick drawn as a circle carrying its
  sheet rank, the anchor with its precision circle, the search radius, and the numbered tiles of the
  `cut_grids.py` grid for the same piece. A person can go from a thumbnail to its place on the ground to
  the full-resolution grid tile without reading coordinates.
- Every pick in `suggestions.json` and the Markdown table carries `grid_tile`, the number of the
  `cut_grids.py` tile it falls in (none when it lies outside the 1.5 km square; the circle is wider than the
  square). `grid_layout` in `landers/sheets.py` is now the one place that arithmetic lives, and
  `crop_site.render_grid` reads its window from it, so the numbers on the tiles and in the suggestions
  cannot drift apart.
- Per piece and strip, `suggestions.json` records how many candidates lay within the radius, the branch mix
  of the top 50, the top and 50th scores, how many picks the grid covers, and the nearest pick to the anchor
  with its rank. Thumbnails are 128 px (32 m) instead of 96 px (24 m), so a 12 m parachute has ground around it.
- `docs/plan.md` carried two observation ids in a timing rule, which failed the leak check and the test that
  runs it; the rule now points at docs/data.md for the names. The branch was red before this change.
- Tests: grid numbering (centre tile, corners, outside, clipping at the image origin), the map drawing on a
  synthetic window (a mark at every pick, the grid drawn), and the script end to end on a hand-built
  candidates file against the Viking 1 strip (ranks, line and sample, grid tile in or out, no write to the key).
  48 tests green with the strips on disk; ruff clean; leak check clean over 59 files.

Rerun: `out/baseline_v1/sheets/` rebuilt from the baseline lists (commit 3c59e16), 30 sheets, 30 maps,
`suggestions.json`, `suggestions.md`, log in `out/baseline_v1/sheets.log`.

## Numbers

From `out/baseline_v1/sheets/suggestions.json` (top 50 within 1500 m; strips named by site and date order,
the file keys them by id; "in grid" is how many of the 50 fall inside the 1.5 km `cut_grids.py` square):

| site | piece | strip | within 1.5 km | top 50 branches | score top..50th | in grid | nearest pick |
|---|---|---|---|---|---|---|---|
| schiaparelli | crash_scar, backshell | first date | 16634 | sheet 50 | 6.43..2.06 | 24 | #18 at 152 m |
| schiaparelli | crash_scar, backshell | second date | 20975 | sheet 50 | 5.56..2.08 | 24 | #19 at 134 m |
| schiaparelli | parachute | first date | 14006 | sheet 50 | 6.43..1.96 | 14 | #31 at 283 m |
| schiaparelli | parachute | second date | 16603 | sheet 49 dark_compact 1 | 5.99..1.85 | 14 | #24 at 229 m |
| schiaparelli | heat_shield | first date | 14688 | sheet 50 | 6.43..1.99 | 20 | #38 at 100 m |
| schiaparelli | heat_shield | second date | 21254 | sheet 47 dark_compact 3 | 7.01..1.83 | 17 | #1 at 89 m |
| curiosity | parachute | | 4512 | dark 30 dark_compact 18 sheet 1 bright 1 | 5.59..-0.13 | 21 | #7 at 93 m |
| curiosity | backshell, rover | | 5133 / 5131 | dark 30 dark_compact 18 sheet 1 bright 1 | 5.59..-0.12 | 17 | #16 at 213 m / 316 m |
| curiosity | heat_shield | | 3550 | dark 14 dark_compact 13 bright 12 sheet 10 shadow 1 | 5.59..-0.14 | 21 | #38 at 178 m |
| curiosity | descent_stage | | 5441 | dark 39 dark_compact 10 sheet 1 | 5.59..-0.17 | 21 | #29 at 30 m |
| phoenix | lander | first date | 1152 | dark 23 dark_compact 21 sheet 5 shadow 1 | -0.34..-1.15 | 15 | #46 at 157 m |
| phoenix | lander | second date | 7223 | dark 36 dark_compact 13 bright 1 | 0.28..-0.67 | 19 | #50 at 144 m |
| phoenix | backshell | first date | 1131 | dark 24 dark_compact 20 sheet 4 shadow 2 | -0.34..-1.17 | 17 | #1 at 91 m |
| phoenix | backshell | second date | 7060 | dark 34 dark_compact 14 sheet 1 bright 1 | 0.16..-0.67 | 17 | #28 at 119 m |
| phoenix | parachute | first date | 1149 | dark 22 dark_compact 20 sheet 5 shadow 3 | -0.34..-1.17 | 15 | #44 at 200 m |
| phoenix | parachute | second date | 7237 | dark 36 dark_compact 13 bright 1 | 0.28..-0.66 | 19 | #4 at 260 m |
| phoenix | heat_shield | first date | 1176 | dark 24 dark_compact 22 sheet 3 shadow 1 | -0.34..-1.15 | 17 | #14 at 194 m |
| phoenix | heat_shield | second date | 7213 | dark 35 dark_compact 13 sheet 1 bright 1 | 0.28..-0.66 | 21 | #23 at 227 m |
| viking1 | lander | | 1938 | sheet 24 dark 23 dark_compact 3 | 0.18..-0.80 | 20 | #50 at 95 m |
| spirit | lander | | 10481 | dark_compact 22 sheet 10 shadow 6 bright 6 dark 6 | 2.67..0.54 | 14 | #4 at 205 m |
| spirit | parachute, backshell, heat_shield | | 10085 | dark_compact 21 sheet 10 shadow 7 bright 6 dark 6 | 2.67..0.54 | 14 | #4 at 279 m |
| pathfinder | lander | | 745 | sheet 31 shadow 11 dark 8 | -0.68..-1.31 | 14 | #41 at 195 m |
| pathfinder | backshell, parachute, heat_shield | | 899 | shadow 21 sheet 17 dark 11 dark_compact 1 | -0.13..-1.22 | 16 | #18 at 331 m |

(Pieces that share an anchor share a row: Schiaparelli crash scar and backshell; Curiosity backshell and
rover; Spirit's and Pathfinder's pieces without a refined position, which use the published site position.)

A check against the one spot an earlier report flagged by eye (`2026-10-28-branches-injection-grid.md`:
a bright patch with a dark patch on its shadow side near line 40528, sample 14707 on the Viking 1 strip),
from `out/baseline_v1/checks/viking1_eye_spot.json` (written by `experiments/eye_spot_check.py`):
no baseline candidate within 10 m of it; the nearest is a dark_compact 29.2 m away at calibrated score
-1.83, rank 991 of the 1938 within 1.5 km of the anchor. Whether that patch is the lander is for the person
filling the key; if it is, the baseline misses it, and the score will say so.

## What it says, and what it cannot say

- **The top 50 is a thin slice.** Between 745 and 21254 candidates lie within 1.5 km of each anchor; the
  sheet shows the top 50 by calibrated score, 0.2 to 7 percent of them. The `within_radius` number tells the
  person how far down the list the piece can hide if it is not on the sheet.
- **Where the sheet branch dominates (Schiaparelli, 50 of 50 on most pairs), nothing else gets a look.**
  The companion report says what those are: sunlit crater walls. The grid tiles are the way to see the
  pieces there; the sheets are the way to see what the detector would have to beat.
- **The nearest pick is rarely the top pick.** Only two pairs have their closest candidate at rank 1
  (Schiaparelli heat shield second date at 89 m; Phoenix backshell first date at 91 m), and a near pick is
  not a piece: the refined positions are good to 60 to 600 m, so "nearest" measures the anchor, not the
  hardware. Nothing on these sheets is a claim.
- **Picks outside the grid square are real.** 14 to 24 of each 50 fall inside the 1.5 km square the grids
  cover; the rest are in the corners of the circle. The map shows where; a piece outside the square needs
  `cut_grids.py --grid-m` wider or a `crop_site.py --center` at its line and sample.

## Status

- Item 1 is marked done: its report is committed (`2026-10-28-baseline-v1.md`, commit 51e6d16) and the run file
  is on disk with its commit hash. Item 2 is marked done with this report. The interactive session also
  committed a persistence report (plan item 5); that item's status is left for it to set.
- The two sessions worked on the same files and output directory at once. Only each session's own files
  went into its commits; `out/baseline_v1/sheets/` was rebuilt by this session after the other had read it,
  with identical picks.

## What I would do next

Item 3 needs a person: fill the key from the grids, the sheets and the maps. Then item 4, the first score.
The sheets suggest one thing for the person to look at while filling: whether any piece is found by a branch
other than the one that should find it (a backshell as `dark`, a parachute as `bright` rather than `sheet`),
because that decides which branch thresholds the first score will blame.
