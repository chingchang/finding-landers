# Report: search bookkeeping for the open case (2026-10-28)

Plan item 11a, branch `claude/search`. No detector ran. Every number below is copied from a file under
`out/search/` written by `scripts/search.py survey` at this commit (`out/` is not committed; the command
rebuilds the files in under four minutes from the labels and the 1/16 overviews). The rate came from
`out/baseline_v1/run.log` in the worktree where item 1 ran (`.claude/worktrees/repo-overview-plan-e248f3`).

## What was built

`landers/search/`, `scripts/search.py`, `tests/test_search.py`.

- **The grid** (`grid.py`). A square grid in the strips' own polar stereographic frame, 100 m cells. All 34
  search strips share the pole, the centre longitude and the sphere, so a pixel maps to projection metres
  through its label's offsets and scale alone, and footprints compare cell by cell with no registration. A
  label from another frame is refused. A cell counts as covered when half its area holds valid pixels.
- **The inventory** (`inventory.py`). One pass per strip: id, phase, date, Ls, incidence and its tangent, sun
  azimuth, scale, size, valid area, footprint bounds, title, whether the title is the lander search, the
  detector tile count at the detector's own tile size and overlap, and the covered cells.
- **Coverage and overlaps** (`coverage.py`). Union of the cell sets with the number of strips per cell (every
  strip is a different date, so that is dates per cell), area by number of dates, per strip the share of its
  ground seen on a second date, every pair that shares a cell with the shared area and each side's share, and
  the figure: one hue, light to dark with more dates, a legend, a scale bar, the credit line.
- **The plan** (`plan.py`). Tiles per second parsed from a detect.py log's per-strip summary lines; strip
  order (the 2007 PSP strips by date, then the rest by date, a strip whose title is not the search last);
  per-strip seconds; greedy packing into sessions of at most two hours, the loop's limit for one foreground run.
- **The run** (`run.py`, `scripts/search.py run`) for item 11: refuses without `--frozen`, a clean tree and
  an exact tag on HEAD (`--untagged` rehearses), takes the strips in plan order, skips the ones already
  written, and writes `out/search/candidates/candidates_<id>.json` per strip with the commit and tag, so a
  session that ends early loses one strip. Tested with a stub detector on one real strip; never run for real.

## What is on disk (`out/search/inventory.json`)

All 34 `mpl_summer` strips are on disk, none missing. Dates run from 2007-06-30 to 2022-09-16, Ls from
263.77 to 341.49, incidence from 56.79 to 73.38 degrees (tangent 1.528 to 3.349; docs/data.md said 1.5 to
3.3), sun azimuth from 12.85 to 33.71 degrees. 33 strips are at 0.25 m per pixel; the one at 0.5 m is the
dune-field strip ESP_057965_1035, the only one whose title is not the lander search. Valid area over all
strips sums to 2975.3 km2; the grid counts 2976.4 km2, and no strip differs from its own valid area by more
than 0.4 percent.

## Coverage (`out/search/coverage.json`, `coverage.png`)

| dates per cell | km2 |
|---|---|
| 1 | 1383.67 |
| 2 | 506.96 |
| 3 | 171.44 |
| 4 | 15.73 |
| 5 | 0.31 |
| union | 2078.11 |

694.44 km2 of the 2078.11 km2 union has two or more dates, one third. The area spans 44 km by 85 km of
grid. One strip has no second date at all (ESP_058400_1040, 57.75 km2); four strips lie entirely or nearly
entirely on ground that another date also covers (PSP_004336_1035, PSP_004402_1030, PSP_005325_1035,
ESP_031196_1035, fractions 1.0, 1.0, 1.0, 0.998). The per-strip shares are in `coverage.json` under
`per_strip`.

## Overlaps (`out/search/overlaps.json`)

81 pairs share ground; 73 share at least 1 km2 and 38 at least 10 km2. By phase: 37 PSP-to-PSP pairs
(523.0 km2 shared), 19 PSP-to-ESP (286.9 km2), 25 ESP-to-ESP (308.8 km2). The largest:

| pair | km2 shared |
|---|---|
| ESP_013289_1035 and PSP_004336_1035 | 75.32 |
| PSP_005325_1035 and PSP_005602_1035 | 66.32 |
| PSP_004336_1035 and PSP_005114_1035 | 61.26 |
| PSP_004402_1030 and PSP_004969_1035 | 56.41 |
| ESP_013790_1035 and ESP_057965_1035 | 46.15 |
| PSP_004402_1030 and PSP_005035_1030 | 45.50 |
| ESP_075571_1040 and ESP_075663_1040 | 44.87 |

These pairs are the persistence work for item 11: `scripts/persist.py --pair A B` on the per-strip
candidate files, largest overlap first. The PSP strips alone give 37 pairs within one season.

## The tiling plan (`out/search/plan.json`)

The rate is from the eight per-strip lines of the baseline log: 2603 tiles in 5751 s, 0.4526 tiles per
second of wall time, with three worker processes (the baseline report says three). Tiles are 2048 px with
128 px overlap, the detector's defaults.

| | strips | tiles | estimated hours |
|---|---|---|---|
| 2007 PSP strips | 15 | 7177 | 4.40 |
| all 34 | 34 | 14589 | 8.95 |

Packed into sessions of at most 7200 s: five sessions of 7155, 6579, 6224, 7040 and 5234 s, holding 7, 6,
6, 6 and 9 strips. The largest single strip (ESP_013500_1035, 628 tiles) is 1388 s, so no strip needs
splitting below strip level. Two caveats on the estimate: the rate was measured on equatorial and north
polar ground, and the one 0.5 m strip's tiles cover four times the ground of the others at the same
per-tile cost assumed here.

## What I decided and why

- **Grid in the projection frame, not latitude and longitude.** The labels share one frame, so cells line up
  exactly and the overlap of two strips is a set intersection; through latitude and longitude every strip
  would be resampled. The grid records the frame and refuses any other, so a control strip cannot be mixed in
  by mistake.
- **Half-covered cells count; the two area sums agree to 0.4 percent**, which says the threshold neither
  inflates nor trims the footprint at this cell size.
- **The dune strip stays in the plan, last, with a note**, rather than being dropped: docs/data.md calls it
  a bed for false alarms, and whether to search it is a person's call. Its 0.977 share on other dates means
  it costs little to run and gives a same-ground comparison for free.
- **The run refuses to start without a tag.** The plan's timing rule says a frozen tag before the search;
  the script enforces it rather than trusting the prompt, and `--untagged` is there only so item 11 can
  rehearse on one strip before a person tags.
- **No new dependency for the figure.** Pillow draws it; the palette is one hue in six steps, light to dark.

## What I would do next

1. Item 11 proper, after the frozen tag: `scripts/search.py run --frozen --jobs 3` in plan order, five
   sessions; then `scripts/persist.py --pair` over the 38 pairs sharing 10 km2 or more, PSP pairs first.
2. The coverage JSON and figure are ready for the case board (item 12a): `cells` is `[ix, iy, dates]` with
   the grid's definition beside it.
3. A coverage map of what was actually searched (strips with a candidates file, dates per cell among them)
   is the same code over the subset of ids; add `--ids` from the candidates directory when item 11 starts.
