# Report: the tuning loop, third and last session (2026-10-29)

Plan item 8, continued from docs/reports/2026-10-29-tuning-loop.md and -2.md. Both levers were tried. Lever
(a) is calibration per terrain, lever (b) is the fabric branch. Neither passes the item 8 bar, so the
detector the freeze takes scores exactly as before: the v0 table and `landers/shape_v3.json`. No file in
`landers/shape_v*.json`, `landers/calibration_v0.json` or `controls/` changed. Nothing is proposed for
adoption.

Every number is copied from the file named beside it. `out/` is not committed, and each command below
rebuilds its file.

## The reference

The item asked for the shape_v3 reference to be set with a fresh transplant run.
`out/transplant_t4_v3/transplant_t4_v3.json` comes from the t4 command with shape_v3 applied in-process
(`uv run scripts/transplant.py --run t4_v3 --copies 6 --nearest 4 --tiles-per-strip 6 --seed 0`, 213 s).

| board | numbers | file |
|---|---|---|
| injection hardware | 32 of 72 | `out/transplant_t4_v3/transplant_t4_v3.json` |
| injection fabric | 10 of 24 | same |
| injection threshold | 0.302 | same |
| sham hits | 1 of 108 | same |
| key recall@20 | 8 of 18, hardware 7 of 12 | `out/tune/v04_per_strip/tune_v04_per_strip.json`, reference side |

The fresh run equals what `scripts/tune.py` computes offline from t4 under shape_v3. The offline judge and
the in-process detector therefore agree on code at this commit.

## (a) Calibration per strip, detector v0.4

The code came from the previous session, commit 1e53ccc. This session fixed one fault in it, commit
09f7cfb. The per-strip finish had deduplicated across branches by raw score before calibrating. Raw scores
are not comparable between branches, so the wrong copy could survive. It now deduplicates within each
branch before the fit, and across branches on the calibrated scale after it. A test pins this.

**Key pass.** The command was `uv run scripts/detect.py --site curiosity --site spirit --site pathfinder
--site schiaparelli --site phoenix --site viking1 --run v04_per_strip --no-shape-rules --per-strip
--top-exclude 20 --jobs 3 --out out/shape_v4`. It ran at commit 09f7cfb and took 5498 s over the eight
strips (`out/shape_v4/run_v04_per_strip.log`).

**The scale is now uniform.** From `out/shape_v4/per_strip_rates.json` (`uv run
experiments/per_strip_rates.py` on both key runs), candidates per km2 above a calibrated score, over the
eight tuning strips:

| above | nominal | v0 table (v0.3 run) | per strip (v0.4 run) |
|---|---|---|---|
| 0 | 1 | 0.083 to 107.68 | 3.324 to 4.549 |
| 1 | 0.1 | 0 to 14.633 | 0.357 to 0.67 |
| 2 | 0.01 | 0 to 5.437 | 0.096 to 0.155 |

That is what lever (a) asked for. A calibrated score now means about the same rate on every strip. The rate
is still 4 to 15 times the nominal one, because the top 20 of each branch are scored by an extrapolated
tail that falls too fast.

**The key board moves, mostly for the better.** From `out/tune/v04_per_strip/tune_v04_per_strip.json`
(`uv run scripts/tune.py --name v04_per_strip --candidate-key-candidates
out/shape_v4/candidates_v04_per_strip.json --candidate-injection out/transplant_t5/transplant_t5.json
--refit-reference`):

| piece | v0 table rank | per-strip rank |
|---|---|---|
| Schiaparelli parachute | 765 | 8 |
| Schiaparelli heat shield | 31873 | 4231 |
| Schiaparelli backshell | 8 | 15 |
| Schiaparelli crash scar | 51752 | 65992 |
| Curiosity parachute | 3 | 11 |
| Curiosity backshell | 8 | 2 |
| Phoenix lander | 704 | 1446 |
| Phoenix backshell | 2 | 4 |
| Phoenix heat shield | 5 | 18 |
| Pathfinder backshell | 4 | 14 |

Key recall@20 goes from 8 of 18 to 9 of 18, hardware from 7 of 12 to 7 of 12, and no recorded piece leaves
the top 20. The three shape_v3 rules re-measure under the bar: pass fractions 0.003, 0.00093 and 0.00123.
The heat shield and crash scar the plan named stay deep.

**The injection board drops.** Each search tile is scored by its own strip's curves, fitted from 24 other
tiles of that strip. Those curves come from `uv run scripts/calibrate_strips.py --from-transplant
out/transplant_t4/transplant_t4.json --tiles 24 --top-exclude 20 --name t4_top20_24`. The scored run is
`out/transplant_t5/transplant_t5.json` (`--strip-calibration` on that file, `--no-shape-rules`, 222 s).

| | reference | per strip |
|---|---|---|
| injection hardware | 32 of 72 | 29 of 72 |
| injection fabric | 10 of 24 | 7 of 24 |
| threshold | 0.302 | 1.153 |
| sham hits | 1 of 108 | 4 of 108 |

Verdict: REVERT, on injection recall and injection hardware recall.

Why it drops. Two of the nine search strips are almost empty for the raw detector. In 24 tiles, one gave
no candidate and the other gave 6, all sheets. A branch with no curve scores the floor constant, so every
detection on those strips ties at "rare". In t5 without rules, at its threshold of 1.093, PSP_004402_1030 holds 21 kept detections and
PSP_004336_1035 holds 10. Without rules the per-strip t5 keeps 68 detections in all, by the run's own
printout. All four sham hits sit on one tile of PSP_004336_1035, the strip that gave 6 sheets. The
per-strip counts come from `uv run experiments/injection_by_strip.py out/transplant_t5/transplant_t5.json
out/transplant_t4/transplant_t4.json out/strip_cal/t4_top20_24/strip_calibration_t4_top20_24.json`. That
script counts scores strictly above the threshold, so its total over strips can differ by ties from the
run's own count.

**Two repairs, both tried, both reverted.**

- **A minimum population of 50.** A thinner branch is scored by the v0 table. The curves come from `--refit-from` with `--min-population 50`, and the run is `out/transplant_t6`. Hardware reads 31 of 72, fabric 8 of 24, sham 1 of 108, threshold 0.837 (`out/tune/v04_min50_injection_only/tune_v04_min50_injection_only.json`).
- **One table pooled over the nine polar search strips.** This is the per-terrain form of the lever, from `--refit-from --pooled`. The run is `out/transplant_t7_pooled`. Hardware reads 30 of 72 and fabric 5 of 24 (`out/tune/a3_pooled_injection/tune_a3_pooled_injection.json`).

The minimum-population variant was judged on injection only, because it failed there. It got no key pass.

## (b) The fabric branch

These are detector changes in the sheet branch, each run on the injection board first. A key pass, about
90 minutes, would be spent only on a variant that moved the injection board. None did.

| change | injection hardware | fabric | sham | file |
|---|---|---|---|---|
| flatness 0.45, reference | 32 of 72 | 10 of 24 | 1 of 108 | `out/transplant_t4_v3` |
| flatness 0.35 | 32 of 72 | 10 of 24 | 1 of 108 | `out/tune/b1_flat035_injection/` |
| flatness 0.30 | 32 of 72 | 10 of 24 | 1 of 108 | `out/tune/b2_flat030_injection/` |
| flatness 0.40 | 32 of 72 | 9 of 24 | 1 of 108 | `out/tune/b3_flat040_injection/` |
| saturated pixels as data in the sheet branch | 32 of 72 | 10 of 24 | 1 of 108 | `out/tune/b4_sheetsat_injection/` |

Lowering flatness to 0.35 adds 4 sheet detections over the 46 tiles, 8123 against 8119. It trades one
Curiosity canopy planting found for one Spirit canopy planting lost. The saturation variant produces the
identical 8119 detections. No planted canopy on these polar tiles is saturated, so this board cannot judge
the saturated-canopy question. The Pathfinder parachute is 0 of 6 under every variant.

## What I decided, and why

- **Nothing is kept, and the freeze takes the detector as it scores today.** The code default is now
  version v0.4 in table mode. In table mode it scores the same as v0.3. Per-strip mode and the two
  sheet-branch switches exist only behind flags, which default off.
- **Lever (a) is reverted although the key improved.** The bar puts the injection board first, because the
  search runs on ground like it. The per-strip scale fails exactly where the search is quietest. That
  failure is the one that would flood a hand-checked list.
- **No key pass was spent on lever (b).** A detector change that moves nothing on injection is not kept, by
  the e7 precedent in the first session.
- **scripts/run_plan.sh is not part of this commit.** A person's uncommitted edit to it was in the
  worktree. It is left as it was found.

Green: tests pass (`uv run --env-file out/landers.env pytest -q`), ruff is clean over the package, scripts
and tests, and `scripts/leakcheck.sh` is clean.

## What I would do next

1. **Per-strip calibration with an honest tail.** Fit the top of each branch from a split half of the strip
   rather than extrapolating. The realised rate above 2 is 10 to 15 times nominal, and that is the part that
   sets the operating threshold. This is for after the frozen run, as a later tag shown beside it.
2. **A second injection seed** (`--seed 1`), still owed from the first session. Several verdicts here turn
   on one to three plantings.
3. **Saturated canopies need a board that has them.** Plant a cut whose canopy saturates, or choose target
   tiles with brighter ground, before the sheet branch's saturation mask is judged again.
