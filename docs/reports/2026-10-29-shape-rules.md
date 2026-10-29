# Report: shape features into the score, measured against the key (2026-10-29)

Plan item 6. Detector v0.2 records shape and shadow-side features on every bright, shadow and dark_compact
candidate; a versioned rules file can add a measured gain to candidates that pass a physical test and never
lowers one. Three rules were drafted before the false-alarm distributions were seen, then measured on the
eight tuning strips against the key. None meets the draft's own adoption bar, so none is in the score.
The saturation rule comes close and does the most; it is proposed for a person in
`docs/proposals/shape-rules-v1.md`. Along the way the v0.2 saturation change cost one known sheet, which
is fixed here.

## Runs

| run | code | what | file |
|---|---|---|---|
| baseline v1 | 3c59e16 | v0.1, saved before the key existed | `out/baseline_v1/candidates_baseline_v1.json` |
| v02_features | 1fee413 (first two strips, as a dirty 17bac06) and 936bf4b | v0.2 as first built: saturated pixels are data in every branch; features recorded; no rules | `out/shape_v1/candidates_v02_features.json` |
| v02b_features | cd5dc7e | v0.2 with the sheet branch back on the v0.1 mask; features recorded; no rules | `out/shape_v1/candidates_v02b_features.json` |

The detector files did not change between 1fee413 and 936bf4b (the merge brought in scoring v1 and the
model layer only). Both v0.2 runs cover the eight strips of the six tuning sites, 459,313 and 459,307
candidates. Scores are under thresholds v1 (`controls/thresholds.json`).

## What the v0.2 detector changed, before any rule

From `out/shape_v1/rank_compare_v02b.txt` (per-piece ranks from the score files named there):

| run | recall@20 | hardware | median false alarms per km2 | file |
|---|---|---|---|---|
| baseline v1 | 0.15 (2 of 13) | 1 of 9 | 708.21 | `out/baseline_v1/score_baseline_v1_thresholds_v1.json` |
| v02_features | 0.15 (2 of 13) | 0 of 9 | 708.24 | `out/shape_v1/score_v02_features.json` |
| v02b_features | 0.15 (2 of 13) | 1 of 9 | 708.24 | `out/shape_v1/score_v02b_features.json` |

Treating saturated pixels as data instead of holes did what it was meant to in the small-object branches:
two saturated pieces that v0.1 lost to the no-data margin are now candidates, the Viking 1 lander (shadow
branch, rank 1943, 6 saturated pixels; baseline had only a dark_compact at rank 22771) and the Curiosity
backshell (bright branch, rank 55, 69 saturated pixels; baseline had nothing of its own within 5 m). Every
other piece moved by at most two ranks.

It also broke one. In v02_features the Schiaparelli canopy, a sheet at rank 8 in baseline v1 that serves
the backshell under one-to-one matching, disappeared and the backshell went unmatched. On the detector's
own tile the reduced-resolution component has flatness 0.46 with the v0.1 mask (kept, the threshold is 0.45)
and 0.35 with saturated pixels in the block means (dropped): 60 saturated pixels inside the canopy make a
peak, and the sheet test is flatness (`out/shape_v1/sheet_saturation_schiaparelli_parachute.txt`, from
`experiments/sheet_saturation.py`). A saturated pixel is a ceiling, not a brightness, so the sheet branch
alone keeps saturated pixels out of its block means (`DetectorConfig.sheet_saturated_is_data`, default
false, with a test). v02b_features has the sheet back at rank 8. Two things to carry forward: that
detection sits 0.01 above the flatness threshold and reads 0.37 on a window centred on the piece
(`out/shape_v1/sheet_saturation_schiaparelli_parachute_centred.txt`), so it is fragile; and a fully saturated sheet is invisible to this branch under either mask. Transplant injection
(item 7) is the place to measure both.

## The rules, measured

`out/shape_v1/v02b_rules.txt` and `v02b_rules.json`, from `scripts/feature_percentiles.py` on
v02b_features with `out/shape_v1/rules_draft.json`. A rule's pass fraction is over the bright and shadow
false alarms of all eight strips pooled (54,427); a false alarm is a candidate not within the match radius
of a recorded piece. "Pieces" are the recorded pieces with a bright or shadow candidate within the radius.

| rule | test | false alarms passing | gain if adopted | pieces passing |
|---|---|---|---|---|
| shadow_two_sided | two_sided >= 2.0 and shadow height in 0.5 to 3 m | 6039 of 54427, 0.111 | 0.955 | 2 of 5 |
| isolated | no other bright compact object within 100 px | 19284 of 54427, 0.354 | 0.451 | 4 of 5 |
| saturated | at least one saturated pixel | 165 of 54427, 0.003 | 2.518 | 3 of 5 |

The draft's bar was: pooled pass fraction at most 0.05, and the recorded pieces of the covered branches
pass. Shadow and isolation fail the first clause outright: on these strips a two-sided shadow of the right
length is common (one false alarm in nine), and rock fields are not the main false alarm, so isolation
separates nothing. Saturation passes the first clause by a wide margin (per strip, between 0 of 3256 and
126 of 33291) and fails the second: the Curiosity backshell, the Schiaparelli parachute and the Viking 1
lander saturate; the Curiosity heat shield and the Phoenix backshell do not.

## What the rules would do to the score

Rescored with `scripts/rescore.py` from the same candidates, nothing re-detected:

| variant | recall@20 | hardware | file |
|---|---|---|---|
| v02b, no rule | 0.15 (2 of 13) | 1 of 9 | `out/shape_v1/score_v02b_features.json` |
| v02b, saturation rule alone | 0.31 (4 of 13) | 3 of 9 | `out/shape_v1/score_v02b_features_shape_v1sat.json` |
| v02b, all three rules | 0.31 (4 of 13) | 3 of 9 | `out/shape_v1/score_v02b_features_shape_v1.json` |

The saturation rule alone moves the Viking 1 lander from 1943 to 2, the Curiosity backshell from 55 to 9
and the Schiaparelli parachute's bright fragment from 30724 to 760. Its cost is on the Spirit strip: 126
false alarms there carry a saturated pixel, 88 of them overtake the Spirit lander, which goes from rank 22
to 109 (`out/shape_v1/saturated_rule_cost.txt`; those 88 have 1 to 40 saturated pixels, median 2). The
median false-alarm rate cannot move, since a rule changes no count. Adding the other two rules changes no
hit at 20 and lifts 23,043 candidates, which pushes the marks and the Phoenix pieces down; they add nothing.

## What I decided and why

- No rule is applied. Thresholds are proposed by the agent and adopted by a person (docs/plan.md, timing
  rules), and the draft's own bar is not met. The saturation rule is written up as a proposal with the
  numbers above; adopting it is a person's call, as is the bar for the rules that item 8 will try.
- The draft's second clause is close to unsatisfiable for a gain rule: a heat shield is dark and does not
  saturate, and no single physical test covers every kind of piece. The proposal suggests a bar that
  measures the harm directly instead (no recorded piece leaves the top 20, and pooled pass fraction at most
  0.05).
- Saturated pixels stay data in the small-object branches and stay out of the sheet branch, each on a
  recorded piece.

## Observations for item 8, not acted on

From the per-piece feature table in `out/shape_v1/v02b_rules.txt`, with the value and the fraction of
same-branch false alarms on the same strip at or above it. Three of the five covered pieces sit in the top
1.1 percent of edge sharpness (Curiosity heat shield 0.011, Phoenix backshell 0.001, Viking 1 lander
0.003); the two saturated fragments do not. The Phoenix backshell's two-sided shadow contrast of 6.8 is
above every bright false alarm on its strip, and the Phoenix heat shield's 4.0 above every dark_compact one;
the shadow branch already selects on this, which is why the Viking 1 lander's 2.5 is unremarkable there.
Any threshold on these would now be chosen after seeing five pieces; it belongs in the tuning loop with the
injection scoreboard, one change at a time.

## What I would do next

Item 7, transplant injection, which is also the test for the two sheet questions above. If a person adopts
the proposal, `landers/shape_v1.json` is the fitted file `out/shape_v1/v02b_rules_fitted_rules.json`
with the two unadopted rules removed, and `scripts/detect.py` picks it up by default.
