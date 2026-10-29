# Report: persistence between the two Schiaparelli dates and the two Phoenix dates (2026-10-28)

Item 3 of the four. `landers/persist.py` and `scripts/persist.py`, run on the baseline v1 lists
(commit 3c59e16). A candidate on one date is "seen" when the other date's own list has a candidate of the
same family (bright: bright/shadow/sheet; dark: dark/dark_compact) within the persistence radius of its
registered position. Seen on both dates and passing a physical test gives the grade "candidate"; nothing
else raises a grade.

## How registration works

Two stages. The labels alone put the same ground tens of metres apart (Schiaparelli: 219 px by 147 px,
55 m by 37 m; Phoenix: 69 px by 113 px), beyond any practical full-resolution search. A coarse template
match on the 1/16 overviews finds that gross offset at a handful of spots along the strip; a fine template
match of 384 px windows, searched 192 px around the coarse prediction, then runs on a 4096 px grid of
nodes. Nodes with weak or ambiguous peaks, or offsets far from the strip's median, are dropped; a
candidate's offset is interpolated from its nearest good nodes. The remaining spread of good nodes about the
strip median is 5 px on both pairs.

| pair | direction | nodes | ok | median correlation | spread px |
|---|---|---|---|---|---|
| schiaparelli | first to second date | 92 | 28 | 0.45 | 5.4 |
| schiaparelli | second to first date | 30 | 27 | 0.43 | 4.9 |
| phoenix | first to second date | 79 | 73 | 0.77 | 5.3 |
| phoenix | second to first date | 101 | 67 | 0.77 | 5.1 |

Schiaparelli's first strip is three times longer than the second, so most of its nodes have no ground to
match (28 of 92 ok) and 49825 of its candidates are "unregistered": outside the overlap, not scored either
way. The Phoenix pair, same season and similar sun, correlates at 0.77.

## The persistence radius

From `out/baseline_v1/persist_schiaparelli_r20.json` and `persist_phoenix_r20.json` (radius 20 px, the
scoring match radius) against `persist_schiaparelli.json` and `persist_phoenix.json` (radius 8 px):

- True matches sit close: median 2.4 to 3.5 px from the registered position, 90th percentile 5 to 8.6 px.
- At 20 px a random spot lands within range of the dense dark lists 10 to 18 percent of the time on
  Schiaparelli (list density times the circle's area); the injection check, which draws objects into the
  first date that the second cannot contain, found 3 of 35 wrongly seen. At 8 px the chance rate is 1.6 to
  2.9 percent and the check finds 0 of 29 (Schiaparelli) and 0 of 9 (Phoenix).

The persistence radius is therefore 8 px, recorded in each output as `radius_px`, a detector parameter
distinct from the person-owned scoring radius.

## What persists, by branch (radius 8 px; "seen" fractions)

| pair, direction | shadow | bright | sheet | dark_compact | dark |
|---|---|---|---|---|---|
| schiaparelli first to second date | 2 of 7 | 0.40 | 0.37 (0.45 at score >= 0) | 0.52 (0.87) | 0.57 (0.86) |
| schiaparelli second to first date | 4 of 7 | 0.39 | 0.69 (0.80) | 0.40 (0.87) | 0.86 (0.91) |
| phoenix first to second date | 0 of 24 | 0.01 | 0.24 | 0.72 | 0.89 |
| phoenix second to first date | 0 of 17 | 0.04 | 0.07 | 0.13 (0.42) | 0.29 (0.82) |

## What it says

- **Persistence confirms real ground, which includes rocks and crater walls.** On Schiaparelli the high
  scoring sheets (crater walls, see the contact-sheet report) persist at 80 to 90 percent, and strong dark
  compacts and dark patches at about 90 percent. Persistence removes noise and transients, as the brief
  intends; it is a condition for "candidate", not a discriminator against natural features.
- **It removes a great deal on Phoenix.** 99 percent of the first strip's bright candidates and 96 percent of
  the second's are not there on the other date, and only 13 percent of the second strip's 61000 dark
  compacts are seen in the first. That strip is the noisier of the two (791 per km2 against 210); whatever
  those are, they are not on the ground twice.
- **The seen rate rises with calibrated score in every branch** (e.g. dark compacts 0.52 at any score,
  0.87 at score >= 0): a sign the calibrated score is doing its job of ranking real features first.
- **The grade is now in the lists**: every candidate in the persistence outputs carries
  `extra.persist` and the grade "candidate" or "needs second look"; the baseline lists themselves are untouched.

## What I would do next

1. Persistence across the 34 MPL summer strips, which overlap many times over: the same code, strip pairs
   chosen from the footprints. There the asymmetry seen at Phoenix (what one date shows and another does
   not) becomes the main filter.
2. Register once per pair and cache the nodes (`--reuse-nodes` already does this); registration is the
   whole cost, 2 to 6 minutes per direction here.
3. The key: real pieces will show whether hardware persists at the rate crater walls do (it should: it does
   not move) and at what rank.
