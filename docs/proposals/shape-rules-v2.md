# Proposal: three more shape rules, for a person to adopt or refuse

Proposed by the tuning loop (docs/plan.md item 8) on 2026-10-29, from
docs/reports/2026-10-29-tuning-loop.md. The file to adopt is `docs/proposals/shape_v2.json`, a copy of
`out/tune/e9_all_three/e9_all_three_fitted_rules.json` with the basis text filled in; adopting it means
committing it as `landers/shape_v2.json`, which `scripts/detect.py`, `scripts/transplant.py` and the search
then pick up by default. Nothing is applied until then.

Every number below is copied from `out/tune/e9_all_three/tune_e9_all_three.json` (written by
`uv run scripts/tune.py --name e9_all_three --rules experiments/rules/e9_all_three.json` at this commit) unless
another file is named. The key board is the 18-piece `controls/tuning.json` under thresholds v1, rescored
from `out/shape_v1/candidates_v02b_features.json`; the injection board is `out/transplant_t2/transplant_t2.json`
(the t1 command rerun on the current detector; its detections are identical to t1's) with the rules applied
to the recorded features.

## The rules

| rule | branches | test | false alarms passing (pooled, tuning strips) | gain |
|---|---|---|---|---|
| saturated (adopted, unchanged) | bright, shadow | saturated_px >= 1 | 0.003 | 2.524 |
| shadow_strong | bright | two_sided >= 4.0 and shadow_height_m in [0.5, 3.0] | 0.00093 | 3.03 |
| dark_shadow | dark_compact | two_sided >= 3.5 and shadow_height_m in [0.5, 3.0] | 0.0015 | 2.825 |
| tile_top | bright, shadow | tile_rank <= 0 | 0.03537 | 1.451 |

The bar (docs/plan.md item 8): new rules pass at most 0.05 of same-branch false alarms. All three do; the
per-strip fractions are in the tune file under `rule_rows.candidate`.

## What they do

| | key recall@20 | hardware | injection, hardware | fabric | mark | overall | threshold | sham hits |
|---|---|---|---|---|---|---|---|---|
| shape_v1 (reference) | 6 of 18 | 5 of 12 | 31 of 72 | 10 of 24 | 0 of 12 | 0.38 | 0.276 | 1 of 108 |
| shape_v2 (proposed) | 8 of 18 | 7 of 12 | 35 of 72 | 9 of 24 | 0 of 12 | 0.407 | 0.432 | 1 of 108 |

Key ranks that change by more than a few places: Phoenix backshell 41 to 2 (shadow_strong), Phoenix heat
shield 1198 to 6 (dark_shadow), Curiosity heat shield 203 to 46 and the Schiaparelli parachute's bright
fragment 760 to 193 (tile_top); against that, the Viking 1 lander 2 to 5, the Spirit lander 345 to 531, the
Spirit parachute 109 to 177 and the Phoenix lander (dark branch, no features, nothing lifts it) 697 to 1035.
No piece leaves the top 20. Injection plantings found: Curiosity heat shield 2 to 4 of 6, Phoenix backshell 1
to 2, Spirit lander 3 to 4, Spirit parachute 4 to 3.

## What to weigh

1. **Fabric loses one planting.** The bar says injection recall must not drop and it rises overall and for
   hardware, but by kind fabric goes from 10 to 9 of 24. The loss comes from `tile_top` alone
   (`out/tune/e4_tile_top/tune_e4_tile_top.json` shows the same 10 to 9 with that rule by itself): lifted
   bright false alarms raise the common threshold past one Spirit parachute planting. Adopting
   `shadow_strong` and `dark_shadow` without `tile_top` keeps fabric at 10 and gives key 7 of 18, hardware
   6 of 12, injection hardware 32 of 72 (`out/tune/e2_shadow_strong/tune_e2_shadow_strong.json` and
   `out/tune/e3b_dark_shadow_strict/tune_e3b_dark_shadow_strict.json`, each alone).
2. **`tile_top` is a test of the surroundings, not the object.** It asks whether the candidate is the
   strongest bright component in its 2048 px tile, so it depends on the detector's tile grid (fixed in
   `DetectorConfig`, the same in the search) and on how busy the ground is. On the tuning strips it passes
   0.035 of false alarms; on the polar injection tiles, which hold hundreds of bright components each, it is
   a stricter test, so the gain fitted on the tuning strips understates its rarity in the search area. It
   has the weakest physical reading of the four and the broadest pass fraction; it is also the one that lifts
   the most recorded pieces (6 of the 8 piece candidates in the covered branches).
3. **`dark_shadow` rests on one recorded piece.** The Phoenix heat shield is the only dark_compact piece
   candidate that passes; no injection planting is found through it, and the transplanted dark pieces carry
   their source shadows unchanged, so the injection board cannot test it. Its threshold was moved once, from
   3.0 to 3.5, after the 3.0 version lost a fabric planting (`out/tune/e3_dark_shadow/tune_e3_dark_shadow.json`).
4. **The common threshold rises** from 0.276 to 0.432 at 2 false alarms per km2 over the 46 injection tiles,
   because lifted false alarms now sit higher. Recall is measured at that threshold, so the numbers above
   already pay for it, but a search-area list cut at a fixed score would be shorter.
5. **Thresholds were chosen after seeing the pieces**, from the pooled false-alarm quantiles
   (`experiments/feature_quantiles.py`), which is what the tuning loop is for; the held-out run is where
   this is paid back.
