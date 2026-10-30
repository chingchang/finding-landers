# The single-vote rule (item 14), written before any call

The rule of record needs three votes per candidate (`landers.models.wonder.VoteRule`). Votes on the top 100 per strip
would cost three times what the budget allows, so item 14 uses one vote per candidate, and three only in a borderline
band. A vote can lower a grade and never raise one; this does not change.

This rule is used by item 14's measurement on the tuning strips. Using it anywhere else, the search included, is a
person's decision.

## The rule

The first vote is on the plain view (the crop as it is, one standard stretch, no flip).

| First vote | What happens | Grade |
|---|---|---|
| natural, confidence 0.85 or more | no more votes | one step lower |
| natural, confidence 0.70 or more, under 0.85 | two more votes, on augmented views | `VoteRule` on the three: one step lower when two or more say natural at 0.70 or more and none says hardware at 0.70 or more |
| natural under 0.70, hardware, unsure | no more votes | kept |

Saturated pixels are drawn bright in every view of this item (the finding in `docs/reports/2026-10-29-fewshot.md`). The
prompt text is the plain prompt, unchanged.

## Why these numbers

Both come from item 9c's published votes, tabulated by `experiments/vote_stats_9c.py` into `out/deep14/vote_stats_9c.json`
(copied to `docs/reports/2026-10-30-deep-pass/vote_stats_9c.json`). These are tuning sites and the table separates pieces
from false alarms, so the numbers were chosen with the answers in view.

- **0.85 for one vote alone.** No vote on a recorded piece reached it. Over 6 first votes and 12 later votes on piece ids,
  one natural vote reached 0.70 or more, at 0.78. In the same table, 17 of 47 first votes on false alarms are natural at
  0.85 or more.
- **0.70 for the band's floor.** It is the confidence `VoteRule` already requires, so a vote below it never counted toward
  lowering. 13 of the 47 first votes on false alarms fall in the band, and none of the 6 first votes on piece ids.

**What this rests on.** Eighteen votes on eight piece ids is few, and they cover only ranks 1 to 10 of eight strips. Item
14 votes on ranks down to 100 with a new way of drawing crops, so a confident natural vote on a piece may well turn up. The
review checks in item 9c gave natural 0.72 and 0.72 on two pieces; neither reaches 0.85.

**What this gives up.** The first vote alone decides the case, so a candidate lowered at 0.85 never gets a second look,
and a first vote of hardware or unsure can no longer be outvoted. The second costs some false alarms that three votes would
have lowered.

## What the run must report, fixed now

For the combined list, shown beside frozen-v1, on tuning strips, with the four sites sealed for frozen-v1 labelled not
blind:

1. Recorded pieces lowered, each with its votes. **Any recorded piece lowered is reported by name at the top of the
   report.**
2. False alarms cleared above each recorded piece.
3. Pieces that rise into the top 20.
4. Recall at 10, 20, 50, 100 and 250 on the key and the transplant board, before and after the votes.
5. Each strip's share of voted candidates lowered. A strip above 0.9 is flagged: a rule that lowers almost everything on a
   strip would lower a piece there too (the caution in `docs/reports/2026-10-29-model-scoreboard.md`).
6. How many votes the band took, against the price's assumption.

The combined list was chosen after seeing item 13's result (Decisions of 10-30 15:45), so these numbers are optimistic and
decide nothing about adoption. Only the blind run in item 17 can judge it.

## For the person

Adopting this rule for the search or the blind run, and the caps in the report, are yours. Nothing else in the pipeline
reads it: `SingleVoteRule` runs only through `experiments/deep14_run.py`.
