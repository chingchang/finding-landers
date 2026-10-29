# Report: the tuning loop, first pass (2026-10-29)

Plan item 8. A judge that scores one rules change on both scoreboards without re-detecting, nine ideas
through it, three kept as a proposal (`docs/proposals/shape-rules-v2.md`, `docs/proposals/shape_v2.json`),
four written off in `docs/experiments.md`. Nothing in `landers/` changed its score; the adopted
`landers/shape_v1.json` is untouched.

Every number here is copied from a file under `out/tune/<name>/tune_<name>.json`, written by
`uv run scripts/tune.py --name <name> --rules experiments/rules/<name>.json` at this commit, or from
`out/transplant_t2/transplant_t2.json`. `out/` is not committed; the commands rebuild the files in seconds
(the transplant run in about five minutes).

## What was built

- `scripts/transplant.py` applies the newest `landers/shape_v*.json` by default, as `scripts/detect.py` does,
  so the injection board measures the detector the search will run (`--no-shape-rules` records the features
  and adds nothing). Every detection now carries its shape features, so other rules can be applied to a
  recorded run.
- `landers/tune.py`, `scripts/tune.py`, `tests/test_tune.py`. One change in, one verdict out. The key board
  rescores an unruled tuning-strip run (`out/shape_v1/candidates_v02b_features.json`) and scores it against the
  18-piece key under thresholds v1; the injection board applies the rules to the recorded detections of an
  unruled transplant run and recomputes recall at 2 false alarms per km2. The candidate file carries only the
  tests; each rule's pass fraction and gain are measured on the key run's same-branch false alarms before
  either board is scored, so no gain is typed by hand. The bar is the one written in docs/plan.md item 8:
  hardware recall@20 on the key does not drop; injection recall does not drop (overall, and hardware on its
  own, which is stricter than the plan's wording); no piece that was in the top 20 leaves it; every rule not
  in the reference passes at most 0.05 of false alarms. A test pins that the offline application equals
  `landers.detect.finish_tile` on the same candidates.
- `experiments/feature_quantiles.py`: the pooled false-alarm quantiles of every recorded feature beside the
  recorded pieces' values, which is where the thresholds below were read off. `experiments/rules/`: the nine
  draft files.
- `tests/test_board.py`: the blind build now names the demo coverage file; it had been reading the real
  `out/search/coverage.json`, which exists in this worktree since item 11a, and failing the leak guard.

Green: 139 tests (`uv run --env-file out/landers.env pytest -q`), ruff clean, leak check clean over 133 files.

## The reference

`out/transplant_t2/`: the t1 command (`--copies 6 --nearest 4 --tiles-per-strip 6 --seed 0`) rerun on
detector v0.2 with `--no-shape-rules`. Its 8119 detections and 216 placements are identical to t1's, which
ran on v0.1: treating saturated pixels as data changes nothing on these 46 polar tiles. So t1's number
stands, and with the adopted saturation rule applied to the same detections
(`out/tune/ref/tune_ref.json`) the number to beat is:

| | key recall@20 | hardware | injection hardware | fabric | mark | overall | threshold | sham hits |
|---|---|---|---|---|---|---|---|---|
| no rules (t1) | 3 of 18 | 2 of 12 | 16 of 72 | 6 of 24 | 0 of 12 | 0.204 | 0.169 | 1 of 108 |
| shape_v1 | 6 of 18 | 5 of 12 | 31 of 72 | 10 of 24 | 0 of 12 | 0.38 | 0.276 | 1 of 108 |

The saturation rule nearly doubles injection hardware recall, which item 6 could not measure. 

## The loop

One change at a time, each judged against shape_v1:

| name | rule added or changed | pass fraction | key | hardware | inj. hardware | fabric | verdict |
|---|---|---|---|---|---|---|---|
| e1_crisp | edge_sharpness >= 0.27 (bright, shadow) | 0.0534 | 7 of 18 | 6 of 12 | 30 of 72 | 8 of 24 | REVERT: over the bar, injection down |
| e2_shadow_strong | two_sided >= 4.0 and height 0.5 to 3 m (bright) | 0.00093 | 7 of 18 | 6 of 12 | 32 of 72 | 10 of 24 | KEEP |
| e3_dark_shadow | two_sided >= 3.0 and height 0.5 to 3 m (dark_compact) | 0.0033 | 7 of 18 | 6 of 12 | 31 of 72 | 9 of 24 | REVERT: one fabric planting lost |
| e3b_dark_shadow_strict | the same at two_sided >= 3.5 | 0.0015 | 7 of 18 | 6 of 12 | 31 of 72 | 10 of 24 | KEEP |
| e4_tile_top | tile_rank <= 0 (bright, shadow) | 0.0354 | 7 of 18 | 6 of 12 | 34 of 72 | 9 of 24 | KEEP |
| e5_sat5 | saturated_px >= 5 in place of >= 1 | 0.00061 | 6 of 18 | 5 of 12 | 30 of 72 | 10 of 24 | REVERT: one hardware planting lost |
| e7_sheet_peaked | flatness <= 0.55 (sheet) | 0.0274 | 6 of 18 | 5 of 12 | 31 of 72 | 10 of 24 | passes the bar, moves nothing, sham hits 1 to 2: not kept |
| e8 | e2 + e4 | | 7 of 18 | 6 of 12 | 35 of 72 | 9 of 24 | KEEP, superseded by e9 |
| e9_all_three | e2 + e3b + e4 | | 8 of 18 | 7 of 12 | 35 of 72 | 9 of 24 | KEEP: the proposal |

(e6 was never drafted; the numbering follows the draft files.) Key ranks under e9 against shape_v1: Phoenix
backshell 41 to 2, Phoenix heat shield 1198 to 6, Curiosity heat shield 203 to 46, Schiaparelli parachute
fragment 760 to 193, Pathfinder backshell 3 to 1, Curiosity backshell 9 to 6; Viking 1 lander 2 to 5, Spirit
lander 345 to 531, Spirit parachute 109 to 177, Phoenix lander 697 to 1035. The injection threshold rises
from 0.276 to 0.432; sham hits stay at 1 of 108.

## What I decided, and why

- **The injection board applies the adopted rules.** Item 7 left transplant.py without them (its branch
  predates item 6's merge), so t1 measured a detector the search will not run. The reference is now shape_v1
  on t2, and t1 is reproduced exactly so the comparison to item 7's report is direct.
- **Rules are rescored, not re-detected.** A rule only adds to scores of candidates that already exist, and
  the floor is applied before the rules, so applying them to recorded features gives the same file as a
  detector run with the rules (pinned by a test). Nine ideas cost seconds each instead of 77 minutes of
  tuning-strip detection per idea. A detector change would need both runs redone; none was tried.
- **Hardware on its own must not drop on injection**, beyond the plan's wording. A rule that trades a hardware
  planting for two fabric ones would pass the written bar and hurt the search, whose long-lived signature is
  metal (docs/plan.md decisions).
- **e7 is not kept though it passes the bar.** The bar is necessary, not sufficient: CLAUDE.md keeps what
  moves the score. It moved nothing and raised the sham hits, which is the seam being rewarded.
- **e9 goes forward with its fabric cost stated**, rather than e2 + e3b without `tile_top` (fabric intact,
  three fewer hardware plantings). The proposal gives both so the person can choose; `tile_top` is the rule
  with the weakest physical reading and the proposal says so.
- **Nothing in `landers/` is adopted.** The plan reserves that for a person; the loop's output is
  `docs/proposals/shape_v2.json` and the file above.

## What I would do next

1. If shape_v2 is adopted: rerun `scripts/transplant.py --run t3` (the rules now in-process) and confirm it
   matches `out/tune/e9_all_three/tune_e9_all_three.json`'s candidate board; that is the new number to beat.
2. The Phoenix lander and backshell are `dark`-branch detections (ranks 697 and 41 on the key) and the dark
   branch records no features, so no rule can reach them. Recording the shape and shadow-side features on
   `dark` candidates is a feature-only detector change (no score moves) that costs one 77-minute tuning-strip
   run plus one transplant run and would let the loop try rules on dust-covered hardware.
3. A second seed for the injection board (`--seed 1`) before any further rule is proposed, since e3b and e5
   turned on single plantings.
4. The sheet branch's flatness test sits at 0.45 with two recorded canopies at 0.45 and 0.46 and the
   injection hits at a median of 0.615 (`experiments/feature_quantiles.py`): the real canopies are the least
   flat of the sheets. Lowering the flatness threshold is a detector change for the loop's next detector run.
