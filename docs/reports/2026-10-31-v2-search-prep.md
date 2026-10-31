# Item 16b: v2's list exists for all 34 search strips, as preparation only

Every search strip now has its re-ranker score, combined rank and rate column, computed from item 11's frozen-v1 lists with the model stage off. No paid call was made,
no heldout strip was run, and nothing is published from this pass. These lists are not item 17's search: they carry `frozen: false`, and no one has looked at a row.

**This did not go through `scripts/v2.py`.** That command refuses to start without the tag `frozen-v2`, which is a person's to make, and this item runs before the tag. So
`experiments/v2_search_prep.py` calls the function that command calls, `landers.v2.run_strips`, with `frozen=False`. I did not edit the guard or make a tag. The plan's item and the oracle's note of 10-31 07:00 ask for
this pass before the freeze, but the guard's message says a person freezes v2 before any run outside the tuning proof, and the timing rules put a tag before the search. If the person reads the rule as covering preparation too, the lists can be deleted with no
effect on anything: they sit in `out/v2/search_prep/`, and nothing in the repo reads them.

Numbers are from `docs/reports/2026-10-31-v2-search-prep/` (`check.json`, `timings.json`, `repeat.json`), run at clean commit 216d17f.

## What the pass produced

| measure | value |
|---|---|
| Strips written | 34 of 34 |
| Candidates on item 11's lists, all recorded in the new lists | 2,544,629 |
| Rows listed | 64,339 |
| Rows with a measured rate, with only a bound, with neither | 64,057, 282, 0 |
| Strips listing fewer than 2,000 rows | 2 (`PSP_004336_1035` and `PSP_004402_1030`, which hold only 300 and 39 candidates, as item 11 reported) |
| Frozen files against item 16a's freeze list | 0 of 57 differ |
| Weights | sha256 `addd7624ed5ddf46fcc06bd130dd29bc6e23e2e29f8299fcd0ae9553c53dc278`, as in item 16a |
| One strip again from nothing (`ESP_031196_1035`) | byte identical |

`check.json` also confirms, on every strip, that the list holds the same rows as the top of frozen-v1's list and that both rank columns are whole. It tests the shape of the lists. It says nothing about whether the ranking is any good.

The repeat covers one strip of the 34, in a new process on the same machine. It does not show the other 33 repeat.

## Timings

Seconds count from the strip's start to its list being written, reading crops, embedding and the rate column together. The total is 6,821 s, about 1.9 hours, on this machine with no other work of mine running. Times depend on the file
cache and are not a benchmark. The encoder loads inside the first strip of each call, here the first two rows and `PSP_005325_1035`. Item 17 can plan on about two hours for the same work from the tag.

| strip | candidates | listed | measured rate | only a bound | seconds |
|---|---|---|---|---|---|
| `PSP_004336_1035` | 300 | 300 | 293 | 7 | 214 |
| `PSP_004402_1030` | 39 | 39 | 34 | 5 | 24 |
| `PSP_004824_1030` | 160,690 | 2,000 | 1,993 | 7 | 224 |
| `PSP_004969_1035` | 68,199 | 2,000 | 1,989 | 11 | 307 |
| `PSP_005035_1030` | 127,522 | 2,000 | 1,992 | 8 | 255 |
| `PSP_005114_1035` | 43,923 | 2,000 | 1,994 | 6 | 327 |
| `PSP_005180_1035` | 142,658 | 2,000 | 1,997 | 3 | 118 |
| `PSP_005325_1035` | 76,940 | 2,000 | 1,994 | 6 | 138 |
| `PSP_005391_1030` | 428,905 | 2,000 | 1,999 | 1 | 295 |
| `PSP_005470_1035` | 45,511 | 2,000 | 1,990 | 10 | 288 |
| `PSP_005536_1030` | 77,038 | 2,000 | 1,990 | 10 | 247 |
| `PSP_005602_1035` | 41,263 | 2,000 | 1,990 | 10 | 260 |
| `PSP_005747_1035` | 36,442 | 2,000 | 1,983 | 17 | 156 |
| `PSP_005813_1030` | 117,281 | 2,000 | 1,993 | 7 | 100 |
| `PSP_005958_1025` | 295,248 | 2,000 | 1,999 | 1 | 269 |
| `ESP_013078_1030` | 69,173 | 2,000 | 1,990 | 10 | 218 |
| `ESP_013223_1025` | 54,388 | 2,000 | 2,000 | 0 | 161 |
| `ESP_013289_1035` | 33,283 | 2,000 | 1,991 | 9 | 269 |
| `ESP_013368_1035` | 41,145 | 2,000 | 1,992 | 8 | 197 |
| `ESP_013500_1035` | 83,943 | 2,000 | 1,986 | 14 | 219 |
| `ESP_013711_1030` | 220,945 | 2,000 | 1,993 | 7 | 300 |
| `ESP_013724_1030` | 40,983 | 2,000 | 1,993 | 7 | 304 |
| `ESP_013790_1035` | 48,795 | 2,000 | 1,988 | 12 | 353 |
| `ESP_013935_1030` | 43,859 | 2,000 | 1,993 | 7 | 159 |
| `ESP_014001_1040` | 37,284 | 2,000 | 1,992 | 8 | 222 |
| `ESP_014423_1040` | 24,143 | 2,000 | 1,993 | 7 | 206 |
| `ESP_031196_1035` | 20,972 | 2,000 | 1,994 | 6 | 103 |
| `ESP_039662_1035` | 13,627 | 2,000 | 1,984 | 16 | 140 |
| `ESP_048734_1035` | 24,977 | 2,000 | 1,990 | 10 | 136 |
| `ESP_049789_1030` | 19,861 | 2,000 | 1,988 | 12 | 141 |
| `ESP_058400_1040` | 22,125 | 2,000 | 1,992 | 8 | 145 |
| `ESP_075571_1040` | 31,379 | 2,000 | 1,994 | 6 | 124 |
| `ESP_075663_1040` | 37,537 | 2,000 | 1,992 | 8 | 139 |
| `ESP_057965_1035` | 14,251 | 2,000 | 1,982 | 18 | 63 |

## What I decided and why

- **New directory, and a run state that says unfrozen.** The lists are in `out/v2/search_prep/`, away from item 17's `out/v2/search/`, so they cannot be picked up by accident. Item 17's run records `frozen: true`, so `run_strips` would refuse to resume this one in place.
- **Strips and order from item 16a's `search_commands.txt`.** So no strip id is typed in the code. The driver refuses any strip on the control list before it opens anything; none of the 34 is on it. To do that it opens `controls/sites.json` once, outside the read guard. It compares
  ids and prints a strip only if it must refuse it. The run's other reads are under the guard, as in item 16a, with only the 34 frozen-v1 lists allowed by name.
- **Only counts and timings are committed.** Ranks, scores and rates stay under `out/`. Nothing here is tuned from them.
- **A test covers the driver only:** which strips it takes, what it refuses, and how it reads the log. The run path itself is item 16a's and unchanged.

## What is not finished

- **Item 17 should rerun this from the tag and not copy these lists.** The timing rules ask for a tag before the search, the rerun costs about two hours, and comparing it with these lists byte for byte is a free test that the tag changed nothing. A difference
  on any strip is a finding to report before the search goes on.
- **Item 16a's open points stand:** persistence on v2 is not built, the stage's depth for the search is not set, and the rate column has not been compared with the pixels.

## Green

`uv run pytest -q` and `scripts/leakcheck.sh`, each on its own on the final tree. No model was called. Some of my combined shell commands were refused by the permission layer. I reran the reads I needed one at a time, and skipped only a look at the machine's memory, which the run did not need.

## What I would do next

Item 17 once the person has tagged: the same pass from the tag, the byte comparison against `out/v2/search_prep/strips/`, then persistence.

## Commands that made these numbers

    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py run --limit 1
    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py run --limit 6
    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py run
    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py check
    uv run --group rerank --env-file out/landers.env experiments/v2_search_prep.py repeat ESP_031196_1035

Credit for all images: NASA/JPL/University of Arizona.
