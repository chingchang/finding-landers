# Item 13: the learned re-ranker, protocol fixed before any run

Written and committed before the first embedding and the first fit. This is not a proposal to adopt anything. The
decision rule is the person's, from docs/plan.md item 13. The rest is the agent's reading of that item, written here so
it cannot follow the result. A bug fix after this commit is reported as one; a change of design is reported as
exploratory and cannot change the decision.

## Decision rule (docs/plan.md item 13)

Adopt only if leave-one-site-out recall@20 beats frozen-v1 on both boards (key and transplant) and no recorded piece
drops out of the top 20. A tie does not beat. Adoption is a person's, through a proposal in docs/proposals/.

## Encoder

DINOv2 small (facebook/dinov2-small), frozen, weights pinned by the revision the run records. Local, no paid call.
A hard cap of 80,000 crops per pass is enforced in code.

## Crops

Native crops from out/export, 320 px. Each crop:

1. no-data pixels filled with the crop's median;
2. rotated so the sun's direction from the label is the same in every crop;
3. cut to two windows fixed on the ground, 16 m and 56 m, so 0.25 and 0.5 m strips see the same ground;
4. each window scaled by its own median and MAD (MAD floor 2 percent of the median), clipped at 6 either way, so
   saturated pixels are bright and a noise-only crop is not stretched into texture;
5. resized to 224 px.

The features are the CLS token and the mean of the four central patch tokens, for both windows: 1,536 numbers.

## The classifier

Logistic regression, L2, C = 0.1, weights normalised to sum to the number of training rows. Inputs: 64 principal
components of the embedding (fitted on the fold's training rows), the proposer's calibrated score, and the novelty
score; all standardised on the fold's training rows. Nothing is chosen by searching over these numbers.

Novelty: mean cosine distance to the 10 nearest neighbours in the same strip's population, as a z-score within the
strip. The population is the top 2,000 on a tuning strip and the detections in the listed tiles on a target strip.
Under 12 members the novelty is 0.

## Training rows

Positives, half the total weight each way:

- native: a recorded piece's best-ranked candidate crop within its match radius if in the top 2,000, otherwise the crop
  at its recorded position;
- transplanted copies: the best-scoring detection within the match radius of a planting, otherwise the crop at the
  planting's centre.

Negatives, a third of the total weight each:

- the top 200 of each tuning strip holding a recorded piece, minus anything within max(match radius, the piece's size)
  of a recorded piece. Strips with no recorded piece give no negatives: their hardware is there but unmarked.
- sham cuts: the crop at each sham planting's centre, so a paste seam alone earns nothing;
- tile false alarms: detections in the planted tiles matching no real planting. Without these, polar ground itself would
  look like a sign of hardware, because every copy sits on it. These tiles are the 46 listed in the decision of 10-29
  02:00; nothing else from the search area is used.

## Transplant run

A new run, because the existing boards hold 18 pieces and the key now holds 32. Every recorded piece and its sham, four
copies each, planted into the 46 listed tiles from the exported windows, each cut going to tiles of the 4 nearest listed
strips of its scale by tangent of incidence. The detector is frozen-v1's. The frozen-v1 number on this board comes from
this run with the detector's own scores.

## Folds

Ten sites, one held out at a time; every strip of the site, its pieces, copies and shams leave the training rows.

- Key board: each held-out strip's top 2,000 is re-ordered by the model without that site. Candidates below rank 2,000
  keep their order beneath them. A piece not in the top 2,000 cannot rise. A piece the proposer never listed is a miss.
- Transplant board: as the key's, and also holding out the target strip of the detection being scored, because that
  strip's false alarms would otherwise be training rows that set the threshold. For each held-out site, all detections
  are scored by the model without that site and without their own target strip; a threshold is set; only that site's
  copies count. The boards are pooled over the ten folds.

## The numbers

Recall at N for N = 10, 20, 50, 100, 250, frozen-v1 beside the re-ranker, on both boards.

- Key: rank by landers/score.py, one candidate to one piece, thresholds version 1.
- Transplant: the planted tiles are a small part of a strip, so rank N on a strip means a false-alarm rate: N divided by
  the median valid area of the target strips, per km2, over the planted area, by
  landers.score.recall_at_false_alarm_rate. Primary: N = 20. The earlier board's rate from controls/thresholds.json is
  reported beside it and does not decide.

Also reported: recall by kind; per-site recall with mean and standard deviation, not only the pooled number; a 95
percent interval on the pooled numbers (Wilson; copies of one piece are not independent, so the transplant interval is
too narrow, and the report says so). Every number on the four sites sealed for frozen-v1 is labelled "not blind".

## Is it learning the paste?

For each piece, under the model without its site: the native score against the median of its copies' scores. If the
median difference over pieces is above 1.0 in log odds and the copies are higher for at least three quarters of the
pieces, the report says the model is learning the paste, and the re-ranker is not adopted whatever the boards say. Also
reported: real copies against shams and shams against tile false alarms (AUC), and the transplant board split by the two
target strips with no ground texture (docs/reports/2026-10-30-disk-work.md) against the rest.

## Reported beside, never deciding

The same folds with the proposer's score left out, with novelty left out, with the embedding only, and with no
transplanted data at all (native positives, list negatives).
