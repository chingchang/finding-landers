# Item 16: the two-sided test for dark candidates, protocol fixed before any run

Written and committed before the first measurement. This is not a proposal to adopt anything. The decision rule is the
person's, from docs/plan.md items 13 and 16 ("same judging as A"). The rest is the agent's reading of item 16, written here
so it cannot follow the result. A bug fix after this commit is reported as one; a change of design is reported as
exploratory and cannot change the decision.

## Decision rule

Adopt only if leave-one-site-out recall@20 beats frozen-v1 on both boards (key and transplant) and no recorded piece drops
out of the top 20. A tie does not beat. Adoption is a person's, through a proposal in docs/proposals/. Reported for N = 10,
20, 50, 100 and 250 on every board, frozen-v1 beside it. Every number on the four sites sealed for frozen-v1 (perseverance,
insight, zhurong, beagle2) is labelled "not blind".

## Why a new measurement

The recorded `two_sided` starts its bands at the candidate's equivalent radius from its centroid. A dark patch stretched
along the sun axis, which is what a cast shadow is, still has its own pixels at that distance, on both sides, so the
feature reads the patch and not the ground beside it. Item 8 already tried the recorded feature on the `dark` branch
(`dark_branch_shadow`, docs/experiments.md) and it reached no piece. The recorded version is kept here as a comparison.

A dark candidate may also be the shadow itself, not an object beside a shadow. A dust-covered object has about the albedo
of the ground, so what shows is its shadow on the anti-sun side and its lit face on the sun side. A depression gives the
same dark patch the other way round: its shaded wall is on the sun side and its lit wall on the anti-sun side. So the test
is the sign of the relief: the darkness has something lit on its sun side, and nothing dark there.

## The measurement (`landers.shape.relief_features`)

For each `dark` and `dark_compact` component, from the label's sun azimuth and incidence only, on the local z map:

- Project the component's own pixels on the shadow direction and across it, which gives its sun-side edge, its anti-sun
  edge, its length along the axis and its width across it. Strips with incidence under the detector's
  `shadow_min_incidence_deg` get no features and so can pass nothing.
- Two bands as wide as the component, at each pixel step outward from each edge, starting one pixel beyond it and reaching
  the shadow length of a 3 m object plus the same 2 px margin as `shadow_features`.
- `relief_dipole`: the brightest band value on the sun side minus the brightest on the anti-sun side.
- `relief_sun_min_z`, `relief_anti_min_z`: the darkest band value on each side.
- `relief_height_m`: length along the axis as a height, length * scale / tan(incidence). `relief_width_m`: width across.

## The test

A candidate of the branch passes when all hold:

1. `relief_dipole >= T`, with T above 0;
2. `relief_sun_min_z >= -2.0`, the detector's `band_dark_z`: not dark on the sun side;
3. `relief_height_m` in 0.5 to 3, the detector's `shadow_heights_m`;
4. `relief_width_m <= 10`, the top of the detector's `bright_size_m`: hardware is not wider than this, a long trough is.

Conditions 2 to 4 use numbers the detector already has. T is the one fitted number, separately for each branch: over every
listed candidate of that branch on the fitted strips, counted as a false alarm with no truth involved, the value at which
the fraction passing all four conditions comes to p = 0.001. That is the order of the three rules in use (0.00093 to 0.003),
and it is fixed here, not searched. If fewer than that pass with T just above 0, T stays there and the fraction is what it
is. The gain is -log10 of the fraction measured, as for every rule (`landers/shape.py`), added on top of frozen-v1's score
including any shape_v3 gain. A candidate that fails keeps its score. Nothing is dropped.

## Folds

The primary arm is leave one site out: for each of the ten tuning sites, T and the gain are fitted on the other sites' strips
and applied to that site's pieces and to its planted copies. On the transplant board each fold rescores all detections and
only that site's plantings are counted. All other arms below use the fit on all tuning strips.

## The boards

The same as item 15, reusing its code and checks:

- Key: `landers.score` on the full lists of the 14 tuning strips, thresholds version 1, one candidate to one piece. A piece
  the proposer never listed is a miss.
- Transplant: item 13's plantings repeated from its seed, N divided by the median valid area of the target strips, per km2,
  over the planted area. Primary: N = 20. The rate from controls/thresholds.json is reported beside it and does not decide.
  Copies of one piece are not independent, so the Wilson interval on this board is too narrow.
- Frozen-v1 on both boards must reproduce docs/reports/2026-10-30-reranker/summary.json (key 8 of 32 and transplant 15 of 128
  at N = 20); any difference stops the item.

The candidates are frozen-v1's. The detector is rerun over the 14 tuning strips with the features switched on
(`DetectorConfig.relief_features`, default off, so frozen-v1 is untouched) only to measure them. Each strip's rerun must give
the same list as item 15's population (position, branch, raw score, and score within rounding), or the item stops. The 46
transplant tiles are rerun in the same way and must agree with item 13's records. Target strips outside the 46 tiles and the
blind strips are not read.

## Reported beside, never deciding

- `whole_fit`: T and gain from all tuning strips, what a person would adopt.
- `p0005`, `p002`: whole fit at p = 0.0005 and 0.002, to show how much the numbers turn on p.
- `flipped`: a placebo. The whole test with the sun on the wrong side: the dipole's sign reversed and the anti-sun side
  required not dark, fitted to the same p. If this does as well as the primary, the physics is doing nothing.
- `recorded`: the plan's wording on the recorded features: `two_sided >= T` and `shadow_height_m` in 0.5 to 3, same branches,
  same p, whole fit.
- `compact_only`, `dark_only`: whole fit on one branch.
- T, fraction and gain per fold; the fraction per strip under the whole fit (a rule whose fraction is a property of the ground
  is how `tile_top` was withdrawn; docs/proposals/shape-rules-v3-loso.md); the sign of the dipole per strip.
- Sham plantings with a detection at the N = 20 threshold, frozen-v1 and whole fit: a paste seam must not earn this rule.
- Per-site spread and recall by kind.

## Known limits, stated before the run

- I have seen the recorded features of some dark pieces (docs/experiments.md) and that they fail. I have not seen the new
  measurement on any piece. The idea came from physics and from that failure, so it is not independent of the key.
- The boards hold no known dust-covered piece, so they can show what this test costs and whether the dark candidates of
  recorded pieces pass, not whether it finds dust-covered hardware. A win would be a win on hardware that is mostly not
  dust-covered, and a loss does not show the test is useless for dust-covered hardware.
- Frozen-v1's across-branch deduplication may have removed a dark candidate beside a brighter one. Such a candidate is in no
  arm, because the candidates are frozen-v1's.
- A rock is relief too. This test can separate a shadow from a depression, not hardware from a rock.
