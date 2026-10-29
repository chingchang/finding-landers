# Report: the tuning loop, second session (2026-10-29)

Plan item 8, continued from docs/reports/2026-10-29-tuning-loop.md. Three things: (a) the leave-one-site-out
check on `landers/shape_v2.json`, which the adoption note made `tile_top` conditional on; (b) detector v0.3,
features only, so the dark branch and a tile-busyness feature can be reached by rules; (c) the one-change
loop against shape_v2, two ideas, both reverted. Nothing in `landers/shape_v*.json` or `controls/` changed.
The outcome for a person is `docs/proposals/shape-rules-v3-loso.md`: withdraw `tile_top`.

Every number is copied from the file named beside it. `out/` is not committed; each command rebuilds its
file (the key run in 80 minutes, a transplant run in 4 minutes, the rest in seconds).

## (a) Leave-one-site-out

`landers/loso.py`, `scripts/loso.py`, `tests/test_loso.py`. For each tuning site, every rule's pass fraction
and gain is re-fitted on the other five sites' false alarms (both dates of a two-date site go with the site)
and the held-back site's pieces are scored under those gains, on the key and on the injection run (plantings
cut from that site only). The six folds are pooled, and each rule is judged by ablation: the pooled held-out
boards with every rule against the boards with that rule left out. Two questions are kept apart: the plan's
condition (the lift holds on sites the rule was not fitted on) and a stricter one (the pass fraction stays
under the bar on every fold and on every single strip). The check re-fits gains, not the tests' thresholds,
which were chosen in the first session with every piece in view.

From `out/loso/shape_v2/loso_shape_v2.json` (`uv run scripts/loso.py --name shape_v2`, key run
`out/shape_v1/candidates_v02b_features.json`, injection `out/transplant_t2/transplant_t2.json`):

| gains fitted without the scored site | key recall@20 | hardware | injection | hardware | fabric |
|---|---|---|---|---|---|
| no rules | 3 of 18 | 2 of 12 | 22 of 108 | 16 of 72 | 6 of 24 |
| all four | 8 of 18 | 7 of 12 | 44 of 108 | 35 of 72 | 9 of 24 |
| without saturated | 5 of 18 | 4 of 12 | 32 of 108 | 25 of 72 | 7 of 24 |
| without shadow_strong | 8 of 18 | 7 of 12 | 43 of 108 | 34 of 72 | 9 of 24 |
| without dark_shadow | 7 of 18 | 6 of 12 | 44 of 108 | 35 of 72 | 9 of 24 |
| without tile_top | 8 of 18 | 7 of 12 | 42 of 108 | 32 of 72 | 10 of 24 |

The held-out boards with all four rules equal the first session's in-sample boards, so fitting gains without
the scored site changes no outcome. `saturated`, `shadow_strong` and `dark_shadow` hold on both questions
(pass fraction by strip at most 0.00833, 0.00234 and 0.0039). `tile_top`'s lift holds (injection hardware 35
against 32) but its pass fraction is a property of the ground: by strip 0.00634 on the Spirit strip
(ESP_025815_1655, which holds 33289 of the 54424 bright and shadow false alarms) to 0.45351 on the Phoenix
second date (ESP_053451_2485, 699); over the 0.05 bar on five of eight strips; 0.0811 pooled as soon as the
Spirit strip is held back. The pooled 0.035 that met the bar was the Spirit strip's count carrying the rest.

## (b) Detector v0.3, features only

`landers/detect.py` (version `v0.3`): the `dark` branch records the same component, shadow-side and isolation
features as `dark_compact`, and every featured candidate records `tile_count`, the number of components of its
sign in its 2048 px tile. No score moves. Checked on the runs:

- `out/shape_v3/candidates_v03_features.json` (`uv run scripts/detect.py --site curiosity --site spirit
  --site pathfinder --site schiaparelli --site phoenix --site viking1 --run v03_features --no-shape-rules
  --jobs 3 --out out/shape_v3`, commit 0c9e3d4, 4819 s over the eight strips per `run_v03_features.log`):
  every strip's candidate list (position, branch, score) is identical to v02b's; every dark candidate carries
  the features (3176, 2373, 27462, 6863, 738, 51174, 8058 and 13021 per strip, in log order).
- `out/transplant_t4/transplant_t4.json` (the t1 command with `--no-shape-rules`, 219 s): the 8119
  detections and 216 placements are identical to t2's; all 2172 dark detections carry features.
- `out/tune/ref_v03/tune_ref_v03.json` (`--refit-reference` on the v0.3 runs): the four shape_v2 rules
  re-measure to the same pass fractions and gains (0.003 and 2.524, 0.00093 and 3.03, 0.0015 and 2.825,
  0.03537 and 1.451), so `landers/shape_v2.json` needs no re-versioning for v0.3.
- `out/transplant_t3/transplant_t3.json` (the t1 command with shape_v2 in-process, 243 s): hardware 35 of 72,
  fabric 9 of 24, mark 0 of 12, threshold 0.432, sham 1 of 108, equal planting by planting to the first
  session's `out/tune/e9_all_three/tune_e9_all_three.json`. The shape_v2 reference is set.

## (c) The loop against shape_v2

Both on the v0.3 runs (`--key-candidates out/shape_v3/candidates_v03_features.json --injection
out/transplant_t4/transplant_t4.json --reference-rules landers/shape_v2.json`):

| name | rule | pass fraction | key | hardware | inj. hardware | fabric | verdict |
|---|---|---|---|---|---|---|---|
| e10_dark_branch_shadow | two_sided >= 3.0 and height 0.5 to 3 m (dark) | 0.00159 | 8 of 18 | 7 of 12 | 33 of 72 | 9 of 24 | REVERT: reaches no piece, threshold 0.432 to 0.511 |
| e11_tile_top_busy | tile_rank <= 0 and tile_count >= 10 in place of tile_top | 0.0145 | 8 of 18 | 7 of 12 | 32 of 72 | 9 of 24 | REVERT: the injection lift goes with the quiet tiles |

`experiments/dark_features.py` says why no dark rule reaches the key: the Phoenix lander's dark candidate has
two_sided 1.02 and a 0.21 m shadow height, the backshell's 0.74 and 0, the heat shield's is negative.
`experiments/injection_tile_count.py` on t4 says why e11 loses what tile_top gained: of the 43 injection
tiles with a bright detection, 26 hold fewer than 10 bright components (median 4), and the plantings tile_top
lifts sit in tiles with 1 to 6. The shape_v2 proposal's claim that the polar tiles hold hundreds each was
wrong, and is corrected in the new proposal.

Green: 144 tests (`uv run --env-file out/landers.env pytest -q`), ruff clean, leak check clean.

## What I decided, and why

- **Lift and stability are reported apart.** The plan's condition for tile_top was its lift on held-out
  sites, and that holds; the withdrawal is proposed on the per-strip pass fraction, which the bar as written
  (pooled) cannot see. A person decides; the proposal gives both facts and three options.
- **v0.3 is features only, verified by identity.** A detector change would have forced every rule to be
  re-measured and both boards redone; identical candidate lists make the re-measurement a check that passed.
- **Two ideas, not more.** The 80-minute key run took most of the session's compute; the two ideas were the
  ones the new features made possible, and both lost on injection for reasons now understood.

## What I would do next

1. A second seed for the injection board (`--seed 1`), as the first session asked: e3b, e5 and now e11
   turn on one or two plantings each.
2. Leave-one-site-out on the tests themselves: choose each rule's threshold from the other five sites'
   quantiles and score the sixth, since the thresholds are where the key was seen.
3. The sheet branch's flatness threshold (0.45 against recorded canopies at 0.45 and 0.46), a detector
   change for a run with the search in mind.
