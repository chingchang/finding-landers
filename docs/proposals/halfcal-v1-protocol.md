# Item 15: per-strip calibration with an honest tail, protocol fixed before any run

Written and committed before the first fit. This is not a proposal to adopt anything. The decision rule is the person's,
from docs/plan.md items 13 and 15 ("same judging as A"). The rest is the agent's reading of item 15, written here so it
cannot follow the result. A bug fix after this commit is reported as one; a change of design is reported as exploratory
and cannot change the decision.

## Decision rule

Adopt only if recall@20 beats frozen-v1 on both boards (key and transplant) and no recorded piece drops out of the top
20. A tie does not beat. Adoption is a person's, through a proposal in docs/proposals/. Reported for N = 10, 20, 50, 100
and 250 on every board, frozen-v1 beside it. Every number on the four sites sealed for frozen-v1 (perseverance, insight,
zhurong, beagle2) is labelled "not blind".

No parameter is fitted on a recorded piece, so a leave-one-site-out fold would equal the full fit. There are no folds;
the per-site spread is still reported. The shape_v3 rules were measured on an earlier key and sit on both arms alike.

## What is fitted

The candidates are frozen-v1's: the same lists, the same transplant run, no new detector pass and nothing below the
frozen floor. Only the score changes, and only the order follows from it.

1. **The split.** Each strip is a checkerboard of squares 1,000 m on a side, in line and sample, so 0.25 and 0.5 m strips
   split the same ground. A candidate's colour comes from its own position. Each colour's area is its valid area on the
   exported overview. The checkerboard rather than two long halves, because ground changes along a strip.
2. **The curve.** For each branch and each colour, the empirical curve from `landers.calibrate.fit_scores`: rate of raw
   score at or above s, per km2 of that colour, every listed candidate counted as a false alarm. No candidates are left
   out of the knots.
3. **The cross-fit.** A candidate is scored by the curve of the colour it does not sit on, so a real piece cannot lower
   its own rarity.
4. **No extrapolation.** Above the fitted colour's highest raw score in that branch, the data say only that the rate is
   below one in the colour's area. Such a candidate, and any candidate of a branch with no member on the fitted colour,
   gets the same cap, log10(area / 0.5), the bound the module already uses for its floor. Within the cap, order comes
   from frozen-v1's table score, squashed into a span of 0.1 by an arctangent. That order claims no rate.
5. **Rules.** The shape_v3 gain each candidate already has is added afterwards, unchanged.

No number here is chosen by searching. The block size, the cap and the span are fixed above.

## The check on the other half

For each strip, each colour's candidates are compared with the curve from the other colour: candidates at or above a
calibrated level per km2 of the held colour, without rule gains, at levels 0, 0.5, 1 and 1.5 (a level at or above a
strip's cap is not counted for that strip). Reported per branch as realised over nominal, and over all branches together
against nominal times the number of branches. Beside it, at levels 0, 0.5, 1, 1.5 and 2, the frozen-v1 table and the
extrapolated tail of item 8 (`top_exclude` 20, whole strip, in sample). Tuning strips and target strips are reported
apart. This check describes the scale and decides nothing.

## The boards

- Key: `landers.score` on the full lists of the 14 tuning strips, thresholds version 1, one candidate to one piece. A
  piece the proposer never listed is a miss.
- Transplant: the plantings and planted tiles of item 13 (`out/rerank/t10`). The detector is rerun on the saved planted
  tiles to recover raw scores and rule gains, which that run did not write, and must reproduce every recorded detection
  and score; any difference stops the item. Rates as in item 13: N divided by the median valid area of the target strips,
  per km2, over the planted area. Primary: N = 20. The rate from controls/thresholds.json is reported beside it and does
  not decide. Copies of one piece are not independent, so the Wilson interval on this board is too narrow.
- Frozen-v1 on both boards must reproduce the numbers in docs/reports/2026-10-30-reranker/summary.json (key 8 of 32 and
  transplant 15 of 128 at N = 20); any difference stops the item.

## Use of the search strips

The method fits each strip on itself, so the transplant board needs the 9 target strips' frozen-v1 lists
(`out/search/candidates`). Only each candidate's raw score, branch and block are read, for those strips and only to
build curves. No truth is involved and no candidate outside the 46 listed tiles is ranked, looked at or reported. The
decision of 10-29 02:00 keeps tuning inside the 46 tiles, and item 8's third session fitted strip curves from other tiles
in the same way. There is one design here and no search over designs, so the only thing that can pass from those lists
to a choice is the one yes or no of the rule. The report says this again, so the person can overrule it. Blind strips
are refused by code and have no list.

## Reported beside, never deciding

- `shift`: the checkerboard moved by half a block, to show how much the numbers turn on the split.
- `whole_strip`: the same cap, curves from the whole strip, in sample, to show what the split costs.
- `extrapolated`: item 8's tail on these lists (`top_exclude` 20, whole strip).
- `no_rules`: the primary score without the rule gains.
- `better_rank`: each candidate takes the better of its frozen-v1 rank and its primary rank, as in
  experiments/rerank_fusion.py. Nothing this ranks in its first half can leave the top N of frozen-v1's first half, so
  its no-drop result is partly built in.
- The transplant board split by the two target strips with no ground texture (docs/reports/2026-10-30-disk-work.md).
- Per-site spread and recall by kind; how many of each strip's top 20 sit at the cap and which branch they come from.

## Known limits, stated before the run

- Frozen-v1's lists removed across-branch duplicates on the table scale, so a branch's population misses a few objects
  that another branch kept. Few against populations of thousands, and the same on both colours.
- The lists stop at the frozen floor. The top of the curve does not depend on it, and a candidate under it is in no arm.
- Candidates on a quiet strip can reach the cap with low raw scores. The cap there is the honest statement of what that
  strip shows, and the transplant board decides whether it helps.
