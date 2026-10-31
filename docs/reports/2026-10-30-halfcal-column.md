# Item 15a: the half-fitted rate now sits beside each score, and no order changed

The column is in place on the case board and in a copy of each list. Across 35 lists and 2,568,629 rows, no row differs
from its input except for the two new fields. Each input was read back beside its copy by a separate script. Nothing
changes in the detector, the frozen-v1 lists, the rankings or the grades, and no paid call was made.

All numbers are from `docs/reports/2026-10-30-halfcal-column/summary.json`, from a run at clean commit 422fb3d. Line wraps
were the only later change to the runner. Every list here carries no blind result: the 12 tuning strips include the four
sites sealed for frozen-v1, which are **not blind**, and the search strips are the frozen-v1 search lists.

## What the column says

Each row gains two fields, and exactly one is a number:

| field | meaning |
|---|---|
| `half_rate_per_km2` | candidates per km2 of this strip, in this candidate's branch, at or above its raw score, measured on the half of the strip it does not sit on |
| `half_rate_below_per_km2` | above the top of that curve, the data say only that the rate is below this value: one in the area of the other half |

Three limits a reader should keep in mind:

- **The rate is for one branch.** All branches together run higher, about the rate times the number of branches. This is
  the same correction item 15 made to my earlier reading.
- **The rate leaves out rule gains.** A candidate lifted by a shape rule shows the rate of its raw score.
- **It describes how common such a score is on that strip.** It is not a chance that a candidate is hardware. It decides
  no grade.

## Results

| lists | strip lists | rows | rows differing | rows with only a bound | bound rows in the top 20 by score | whole-strip candidates above the curve, per strip |
|---|---|---|---|---|---|---|
| item 14's combined list | 12 | 24,000 | 0 | 118 | 35 of 240 | 6 to 21 |
| frozen-v1 search lists | 34 | 2,544,629 | 0 | 337 | 93 of 680 | 5 to 18 |

Totals of the first three number columns and the per-strip detail are in the summary file.

- **Bound rows at the top of the list.** One strip's top 20 by score holds up to 9 of them (`ESP_049789_1030`). So on many
  strips the top of the list reads "below" and does not give a measured rate. Item 15 said the same: a strip cannot say
  anything about its own top ten.
- **Check against item 15.** On the 12 tuning strips, the count of candidates above the curve equals item 15's
  `at_cap_in_strip` for every strip, and the runner stops if it does not. The 34 search strips have no such reference,
  because item 15 did not record that count for them.
- **Rates vary widely between strips.** A strip's median rate runs from 0.121 to 1,740 per km2 over the search lists. The
  two ends are `PSP_004402_1030` (39 candidates) and `PSP_005391_1030` (428,905 candidates). I did not look at why.

## What the tests hold

- Sorting by score gives the same order with and without the column in each consumer: `score.py`, the model scripts'
  `top_candidates`, the export's `rank_top`, the search's `survivors` and the board. The test list has ties in the score.
- Any other change to a row, or a swap of two rows, is caught.
- On the board, each rate is a traced span with its file and JSON path. A bound row reads "below" and then the value. A
  list without the column shows a dash.
- The rate does not reach a review prompt: Spark's whitelist of candidate fields does not include it.
- A list holding a blind strip is refused, as is a row with no match in the strip's population.

The board built from the copy of the combined list shows 205 measured rates and 35 bounds across its 240 rows.

## What I decided and why

- **The column goes in a new copy under `out/halfcal/column/`.** The inputs stay byte for byte, so frozen-v1's files are
  untouched and item 14's inputs do not move under it.
- **Curves are fitted on each strip's whole population, not on the rows of the list.** Item 14's list holds only the top
  2,000 of a strip and no raw scores, so each row is joined to the population on position and branch.
- **A bound is reported as one in the other half's area.** That is what the data say. The score's cap uses half a
  candidate per area as a position on its scale, and I did not carry that into a rate nobody measured.

## What is not finished, and what you may want to read differently

- **The final v2 list does not exist yet.** The combined list is the v2 list as it stands, and no candidate file has been
  published. When item 17 freezes the list and writes the files to publish, `uv run scripts/halfcal.py column <list>` has
  to be run on them. Nothing runs it automatically.
- **Raw scores of all 34 search strips were read.** Item 15 read 9 of them. The other 25 were read now, because the column
  needs each strip's curve, and those populations were saved under `out/halfcal/pop/`. No truth was involved, no candidate
  was looked at, and nothing was tuned or reordered. The decision of 10-29 02:00 limits tuning to the 46 listed tiles; I
  read this as a report and not as tuning, and you may read it differently.
- **Nobody has compared these rates with the pixels.**

Green: `uv run pytest -q` and `scripts/leakcheck.sh`. `uv run ruff check` flags the five long lines `scripts/halfcal.py`
already had and nothing in the new code.

## Carried over from the session that ended early

An earlier session stopped with a merge open and uncommitted work. I resolved `docs/plan.md` the way main had resolved it,
then committed everything as work in progress. That commit includes a `docs/reports/ledgers.json` row for item 14. The row
came from a run attempt of 10-30 18:40 that stopped before any call: `out/deep14/CHECKPOINT.json` reads 0 calls and 0 USD
for that run, with the wonder cap refusing 1,328 calls because 340 remained. Item 14 stays paused.

## What I would do next

Item 14's paid run is the next open step in the v2 list, and it needs a person's window with the key and a Wonder cap of at
least 1,328 calls.

## Commands

    uv run scripts/halfcal.py column out/deep14/inputs/candidates_combined.json out/search/candidates/candidates_*.json
    uv run experiments/halfcal_column_check.py out/deep14/inputs/candidates_combined.json out/search/candidates/candidates_*.json
    uv run scripts/board.py out/halfcal/column/candidates_combined.json --models out/none --coverage out/none.json --persist --top 20 --out out/halfcal/column/board/combined.html

Credit for all images: NASA/JPL/University of Arizona.
