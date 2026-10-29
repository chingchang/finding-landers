# Proposal: two changes to the scoring, for a person to adopt or refuse

Proposed by the agent on 2026-10-28 after the first score (docs/reports/2026-10-28-first-score.md). The
scoring script and the thresholds are owned by a person; nothing here is applied.

## 1. One candidate matches at most one piece

Today a piece is a hit when any candidate within the match radius ranks in the top N, and the same
candidate may serve several pieces. In the first score the Schiaparelli parachute and backshell are
recorded 21 px apart and the one sheet candidate at rank 8 is within 20 px of both, so one detection
counts as two of the three hits (`out/baseline_v1/score_baseline_v1.json`).

Proposed: assign candidates to pieces greedily in score order, each candidate to the nearest unassigned
piece within the radius, each piece to its first assigned candidate. The parachute keeps the rank-8 hit;
the backshell is scored on whatever else lies within 20 px of it, and today that is nothing. Recall at 20
on the first score would then read 2 of 13.

This is a change to `landers/score.py` and would make the number harder, never easier. If adopted, the
first score is rescored with the same baseline file and both numbers are shown.

## 2. Report hardware and marks apart

Two recorded pieces are not hardware: the Schiaparelli crash scar (a 20 by 12 m dark patch) and the
Curiosity descent-stage mark (a 40 m dark fan with debris at one end). Their recorded point is one place on
an extended mark, and a 5 m radius asks the detector to put a centroid within 20 px of that place. In the
first score the scar is matched 17.7 px off and the fan's nearest candidate is 38.4 m away.

Proposed: keep both in the key and in the headline recall (they are known answers), but add two lines to
the report, recall over hardware pieces (lander, backshell, heat shield, descent stage, rover) and recall
over marks (crash scar, parachute and any other fabric or impact mark), so the number the search depends on,
hard metal at 2 to 3 m, can be read on its own. No threshold changes. A larger radius for marks is not
proposed; the person who owns the thresholds may prefer it, in which case the radius should be written per
piece kind in `controls/thresholds.json`, not inferred from `size_m` in the key.
