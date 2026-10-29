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
