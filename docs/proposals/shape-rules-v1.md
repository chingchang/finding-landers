# Proposal: one shape rule into the score, for a person to adopt or refuse

Proposed by the agent on 2026-10-29 after plan item 6 (docs/reports/2026-10-29-shape-rules.md). Rule
thresholds are adopted by a person; nothing here is applied.

## The rule

`saturated`: a bright or shadow candidate with at least one pixel at the sensor's saturation gains 2.518
on the calibrated scale, which is minus log10 of the fraction of bright and shadow false alarms on the
eight tuning strips that carry one (165 of 54427, 0.00303, pooled; per strip from 0 of 3256 to 126 of
33291). A candidate without one keeps its score. The threshold, one pixel, was written before the
distributions were seen (`out/shape_v1/rules_draft.json`); the fraction and gain were measured by
`scripts/feature_percentiles.py` (`out/shape_v1/v02b_rules.txt`). The file to adopt is
`out/shape_v1/v02b_rules_fitted_rules.json` with the `shadow_two_sided` and `isolated` rules removed,
committed as `landers/shape_v1.json`.

## What it does, measured on v02b_features (`out/shape_v1/rank_compare_v02b.txt`)

| | recall@20 | hardware | file |
|---|---|---|---|
| without | 0.15 (2 of 13) | 1 of 9 | `out/shape_v1/score_v02b_features.json` |
| with | 0.31 (4 of 13) | 3 of 9 | `out/shape_v1/score_v02b_features_shape_v1sat.json` |

Gains: Viking 1 lander 1943 to 2, Curiosity backshell 55 to 9, Schiaparelli parachute (bright fragment)
30724 to 760. Cost: Spirit lander 22 to 109, overtaken by 88 saturated false alarms on its strip
(`out/shape_v1/saturated_rule_cost.txt`). The median false-alarm rate does not change. Pieces that do not
saturate (Curiosity heat shield, Phoenix backshell) keep their rank.

## Why it is a proposal and not a change

The draft set its own bar: pooled pass fraction at most 0.05, and every recorded piece of the covered
branches passes. The rule meets the first (0.003) and not the second (3 of 5 pieces saturate). The second
clause asks one physical test to cover every kind of piece, which no test will; the measured harm is the
better question. Two things to decide:

1. Adopt `saturated` as `landers/shape_v1.json`, or not.
2. The bar for rules that the tuning loop (item 8) will try, suggested: pooled false-alarm pass fraction at
   most 0.05 on the tuning strips, no recorded piece leaves the top 20, and the fraction and gain are
   re-measured and the file re-versioned whenever the detector changes.

A note on the two gains. Both saturated pieces are metal under a high sun; the search area is polar and the
sun is lower there, so saturation may be rarer in the search strips than on these. The rule can only add,
so a search strip with no saturated hardware is unaffected by it.
