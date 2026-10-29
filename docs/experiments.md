# Experiments

One line per idea that did not move the score. Winners go into the main package through a normal change.

- 2026-10-29, item 6: shape rule `shadow_two_sided` (two-sided shadow contrast >= 2 and shadow height 0.5 to 3 m,
  bright and shadow branches): 0.111 of false alarms pass, gain 0.955; added to the saturation rule it changes
  no hit at 20 (0.31 either way) and pushes the marks down. Not adopted. `out/shape_v1/v02b_rules.txt`,
  `out/shape_v1/score_v02b_features_shape_v1.json`.
- 2026-10-29, item 6: shape rule `isolated` (no other bright compact object within 100 px): 0.354 of false alarms
  pass, gain 0.451; rock fields are not the main false alarm on these strips. Not adopted. Same files.
- 2026-10-29, item 6: saturated pixels as data in the sheet branch: the Schiaparelli canopy sheet (rank 8 in
  baseline v1) fails the flatness test (0.35 against 0.46 with the v0.1 mask) and the backshell goes unmatched.
  Reverted for the sheet branch only. `out/shape_v1/sheet_saturation_schiaparelli_parachute.txt`,
  `out/shape_v1/score_v02_features.json` against `score_v02b_features.json`.
- 2026-10-29, item 8: rule `crisp` (edge_sharpness >= 0.27, bright and shadow): 0.0534 of false alarms pass, just
  over the bar; key 7 of 18 but injection hardware 31 to 30 and fabric 10 to 8 as the threshold rose 0.276 to
  0.611. Reverted. `out/tune/e1_crisp/tune_e1_crisp.json`.
- 2026-10-29, item 8: rule `dark_shadow` at two_sided >= 3.0 (dark_compact): 0.0033 pass, Phoenix heat shield
  1198 to 7 on the key, but one fabric planting lost on injection (0.38 to 0.37). Reverted; the 3.5 version
  passed and is in the proposal. `out/tune/e3_dark_shadow/tune_e3_dark_shadow.json`.
- 2026-10-29, item 8: `saturated` threshold raised to 5 pixels in place of 1: 0.00061 pass, gain 3.217; key
  unchanged at 6 of 18 (Spirit parachute 109 to 41, Pathfinder backshell 3 to 1) but one Phoenix backshell
  planting lost on injection (hardware 31 to 30). Reverted. `out/tune/e5_sat5/tune_e5_sat5.json`.
- 2026-10-29, item 8: rule `sheet_peaked` (flatness <= 0.55, sheet): 0.0274 pass, passes the bar but moves no
  number on either board and raises the sham hits from 1 to 2 of 108. Not kept.
  `out/tune/e7_sheet_peaked/tune_e7_sheet_peaked.json`.
- 2026-10-29, item 8 (second session): dark-branch features (detector v0.3) reach no recorded piece. The Phoenix
  lander's dark candidate has two_sided 1.02 (top 0.061 of its strip's dark false alarms) and a shadow height of
  0.21 m; the Phoenix backshell's 0.74 and 0; the heat shield's is negative. No test under the 0.05 bar
  separates them. `experiments/dark_features.py` on `out/shape_v3/candidates_v03_features.json`.
- 2026-10-29, item 8 (second session): rule `dark_branch_shadow` (two_sided >= 3.0 and shadow height 0.5 to 3 m,
  dark branch): 0.00159 pass, gain 2.8, reaches 0 of 5 piece candidates; key unchanged at 8 of 18, injection
  hardware 35 to 33 as the threshold rose 0.432 to 0.511. Reverted.
  `out/tune/e10_dark_branch_shadow/tune_e10_dark_branch_shadow.json`.
- 2026-10-29, item 8 (second session): rule `tile_top_busy` (tile_rank <= 0 and tile_count >= 10, bright and
  shadow) in place of `tile_top`: 0.0145 pass, under the bar on every strip, key unchanged at 8 of 18, but
  injection hardware 35 to 32: the plantings tile_top lifts sit in tiles with 1 to 6 bright components.
  Reverted. `out/tune/e11_tile_top_busy/tune_e11_tile_top_busy.json`, `experiments/injection_tile_count.py`.
