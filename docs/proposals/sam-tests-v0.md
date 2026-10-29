# Proposal: limits for the SAM mask tests (v0, rewritten from the first real masks)

Status: proposed by the agent on 2026-10-28 with plan item 9 and rewritten on 2026-10-29 from the first
twenty real masks (plan item 9b); waits for a person. Until adopted the values live in
`landers/models/sam.py` (`SamLimits`) and every SAM record names them.

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

## What twenty real masks say

From `docs/reports/2026-10-29-first-real-run/summary.txt` (section SAM), the top 20 of one tuning strip
(17 sheet, 2 bright, 1 shadow candidates), 256 px crops, the box padded by the blob's own radius:

- Every box returned a mask. Confidence ran from 0.52 to 0.844, median 0.688, so the 0.3 floor never
  decided an outcome. Keep it; it has not been tested by a weak mask yet.
- The mask touched the box edge in 9 of 20 cases, and that alone made all three tests `unsure` for them.
  The one recorded piece in the twenty, a parachute canopy, was one of the nine (equivalent diameter
  24.31 m, box 99 px). The reviewer's zoom pass on it (512 px crop, box padded 1.5 times) came back inside
  the box: 23.27 m, edge contrast 2.0, size and edge both `pass`. For the sheet branch the default padding
  of 1.0 is too tight for an object whose mask spreads to the detector's blob edge.
- Masks fragment: 1 to 45 connected pieces, median 5.5; the measurements are of the largest piece. The
  canopy's mask had 13 pieces at 256 px and 19 at 512 px, so fragmentation is not a mark of a false alarm.
- Edge contrast: 10 pass, 1 fail (0.79), 9 unsure. The canopy's values were 1.94 and 2.0. The limit of 1.0
  is not contradicted by this strip; it has not separated anything yet either, because 9 of 20 never
  reached it.

Outcomes over the twenty: `sam_size` 11 pass, 9 unsure; `sam_shape` 1 pass, 2 unsure, 17 not run;
`sam_edge` 10 pass, 1 fail, 9 unsure.

## What to adopt, and what to change first

1. The three limits as in the table: no measured reason to move any of them.
2. Before the limits are adopted, pad the sheet branch's box by 1.5 times the blob radius (what the zoom
   pass already does), so that `touches_box_edge` stops being the main outcome; then re-measure. This is a
   change to `landers/models/run.py` (`SamPassConfig.pad` per branch), not to a threshold, and is for the
   next model-layer change, not this proposal.
3. A `touches_box_edge` mask stays `unsure`: on this strip it was the honest outcome for the one real piece
   at 256 px, and the zoom pass is the bounded way to resolve it.
