# Proposal: limits for the SAM mask tests (v0)

Status: proposed by the agent on 2026-10-28 with plan item 9; waits for a person. Until adopted the
values live in `landers/models/sam.py` (`SamLimits`) and every SAM record names them.

The mask SAM 3.1 returns for a box prompt gives three tests an outline to measure. The size limits are not
new numbers: they are the detector's own per-branch size ranges (`DetectorConfig`: bright and shadow 1 to
10 m, sheet 8 to 25 m, dark compact 1 to 4 m, dark 2.5 to 50 m), applied to the mask's equivalent diameter
instead of the thresholded blob's area. Two limits are new and are the ones to adopt or change:

| test | measurement | proposed limit | outcome |
|---|---|---|---|
| sam_size | equivalent diameter of the mask, m | the branch's size range | pass inside, fail outside |
| sam_shape | elongation, 1 - sqrt(minor/major) of the mask's second moments | at most 0.6 (an axis ratio of about 6 to 1), compact branches only | pass at or below, fail above; not run for sheet and dark |
| sam_edge | mean inside the mask minus the mean of a 2 px ring outside, over the ring's std | at least 1.0 | pass at or above |

All three come back `unsure`, not fail, when SAM's confidence is below 0.3 or the mask touches the box
edge (SAM may have segmented the surroundings), and `not run` when there is no mask. A test can only
pass, fail, come back unsure or not run; no candidate is promoted because SAM found a mask.

Why these values: 0.6 elongation keeps every published hardware piece (the longest, a parachute canopy,
is excluded from the shape test anyway) while failing dune crests and crater rims, which run far past 6 to
1 inside a 256 px crop. The edge contrast of 1 sigma is the weakest limit that still separates a real
outline from a stretch of flat ground inside a box. Neither value has been measured on a real mask yet;
item 9b's twenty SAM calls on one tuning site are the first measurement, and this proposal should be
rewritten from that results file before anything is adopted into `controls/thresholds.json`.
