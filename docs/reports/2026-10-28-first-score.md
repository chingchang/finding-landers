# Report: first score, baseline v1 against the key (2026-10-28)

Item 4. The blind number. The baseline v1 lists (`out/baseline_v1/candidates_baseline_v1.json`, code at
commit 3c59e16, saved 2026-10-28 14:32 before the key existed) scored against `controls/tuning.json` as
committed in 1c49e19 (13 of 22 pieces filled by a person) with `controls/thresholds.json` version 0 (5 m
match radius, top 20, pass at recall 0.8 and 2 false alarms per km2).

```
uv run scripts/score.py out/baseline_v1/candidates_baseline_v1.json --out out/baseline_v1
```

## The number

From `out/baseline_v1/score_baseline_v1.json`:

```
recall@20 = 0.23 (3/13 recorded pieces)   median false alarms/km2 = 708.21   FAIL
```

The detector does not pass. Three of the thirteen recorded pieces sit in the top 20 of their strip, and
the lists are 350 times longer than the pass line allows, because baseline v1 kept everything down to a
calibrated score of -3 on purpose (the key was to be filled from its tails).

Two things make the 0.23 kinder than it is:

- **Two of the three hits are one detection.** The Schiaparelli parachute and backshell are recorded 21 px
  apart; the one sheet candidate at rank 8 is within 20 px of both, so it counts twice. Distinct hardware in
  the top 20: two parachutes, nothing else.
- **Two of the thirteen positions came from the detector's own sheets** (the Schiaparelli parachute is sheet
  pick 1, the Spirit lander is sheet pick 4, per the key's notes). The other eleven came from registered
  caption images or the stretched grids and are independent of the lists.

Nine pieces have no recorded position and are not scored (Curiosity rover; Phoenix parachute; Spirit
parachute, backshell, heat shield; all four Pathfinder pieces). They are not counted as misses.

## Per piece

Whole-strip rank is the scored number. Local rank is the rank within 1.5 km of the recorded position (the
contact-sheet view). Branch rank is the rank among that branch's candidates. Above op: whether the matched
candidate clears 0.873, the threshold the phase 1 injection evaluation set for 2 false alarms per km2
(`out/inject_eval_p1_cal.json`). All from `out/baseline_v1/score_baseline_v1.json` and
`out/baseline_v1/score_baseline_v1_diag.json` (written by `experiments/first_score_diag.py`).

| site | piece | rank | local | branch rank | branch | score | raw | above op | nearest candidate |
|---|---|---|---|---|---|---|---|---|---|
| schiaparelli | crash_scar | 51685 | 8629 | 35212 | dark | -1.41 | 2.59 | no | 4.4 m, dark |
| schiaparelli | parachute | 8 | 1 | 8 | sheet | 6.43 | 10.41 | yes | 2.9 m, sheet |
| schiaparelli | backshell | 8 | 1 | 8 | sheet | 6.43 | 10.41 | yes | 2.5 m, the same sheet |
| schiaparelli | heat_shield | 31799 | 3978 | 22387 | dark | -1.14 | 2.91 | no | 0.9 m, dark |
| curiosity | parachute | 3 | 1 | 3 | sheet | 5.59 | 9.64 | yes | 1.7 m, sheet |
| curiosity | backshell | miss | | | | | | | 28.6 m, dark_compact |
| curiosity | heat_shield | 201 | 30 | 49 | bright | -0.15 | 11.08 | no | 0.8 m, bright |
| curiosity | descent_stage | miss | | | | | | | 38.4 m, dark |
| phoenix | lander | 696 | 41 | 344 | dark | -1.13 | 2.92 | no | 1.5 m, dark |
| phoenix | backshell | 40 | 2 | 23 | dark | -0.34 | 3.80 | no | 0.1 m, bright (rank 999) |
| phoenix | heat_shield | 1197 | 73 | 462 | dark | -1.32 | 2.70 | no | 0.3 m, dark_compact (rank 4368) |
| viking1 | lander | 22771 | 983 | 4500 | dark_compact | -1.83 | 5.70 | no | 2.0 m, dark_compact |
| spirit | lander | 21 | 4 | 4 | sheet | 1.87 | 6.27 | yes | 0.1 m, sheet |

Recall at N over the 13 recorded pieces, whole-strip rank (`score_baseline_v1_diag.json`, `recall_at`):

| N | 10 | 20 | 50 | 100 | 250 | 1000 | 5000 |
|---|---|---|---|---|---|---|---|
| found | 3 | 3 | 5 | 5 | 6 | 7 | 8 |

Per strip (`score_baseline_v1.json`, `strips`; `score_baseline_v1_diag.json`, `strips`):

| site | strip | candidates | hits | FA/km2 | above op | above op per km2 | pieces above op |
|---|---|---|---|---|---|---|---|
| schiaparelli | ESP_048041_1780 | 3 | 1324.70 | 1158 | 11.38 | 2 of 4 |
| schiaparelli | ESP_073625_1780 | 0 | 2349.07 | 515 | 16.00 | no pieces recorded |
| curiosity | ESP_030313_1755 | 2 | 625.10 | 36 | 1.61 | 1 of 4 |
| phoenix | ESP_017716_2485 | 5 | 210.32 | 1 | 0.01 | 0 of 3 |
| phoenix | ESP_053451_2485 | 0 | 791.32 | 1 | 0.01 | no pieces recorded |
| viking1 | ESP_046170_2025 | 1 | 439.51 | 1 | 0.01 | 0 of 1 |
| spirit | ESP_025815_1655 | 1 | 1381.43 | 159 | 3.12 | 1 of 1 |
| pathfinder | ESP_022038_1995 | 10352 | 0 | 137.69 | 0 | 0.00 | no pieces recorded |

The "hits" column counts candidates within 5 m of any recorded piece, so Phoenix shows 5 for 3 pieces (two
pieces have two candidates each within the radius) and Schiaparelli shows 3 for 4 pieces (the shared sheet).

## What the ranks say

- **The sheet branch finds the big bright things.** Both parachutes are in the top 10 of a 22 to 100 km2
  strip, and the Spirit lander, a 3 m bright platform, is at rank 21, one place outside the line. All three
  clear the 2 per km2 operating point. These are the only pieces that do.
- **Hard metal at 2 to 3 m is where the detector fails**, and that is the long-lived signature the search
  depends on. The Schiaparelli heat shield, the three Phoenix pieces and the Viking 1 lander were all found
  by the dark branches (shadow or dark patch), at calibrated scores between -0.3 and -1.8: the calibration
  says things like them occur hundreds of times per km2 on that ground, and the ranks agree.
- **The bright branch sees two of them and the calibration buries both.** The Curiosity heat shield is a
  bright candidate 3.2 px from the recorded position (raw 11.08) that calibrates to -0.15 and rank 201. The Phoenix
  backshell is a bright candidate 0.3 px from the recorded position (raw 6.78) at rank 999, while its
  70 px shadow, found by the dark branch, is the rank-40 hit. The calibration for bright was fitted to the
  bright branch's false-alarm rate on four sites; on these strips that rate is high and real pieces pay for
  it. Where the branch fires, the shape features (item 6) and the shadow pairing are the way to separate
  them, not a lower threshold.
- **The shadow branch did not fire on any piece.** On the first Phoenix strip it produced 24 candidates in
  84 km2 and none within 40 px of the lander, backshell or heat shield, although the key records a 70 px
  saturated-black shadow beside the backshell. On Viking 1 only a dark-compact candidate sits within 40 px of the lander;
  the bright branch has nothing there. Why the pairing misses a bright object with a 70 px shadow is the
  first thing to look at under item 6; the two-sided shadow test in the second-pass sheets is the candidate
  replacement.
- **Two Curiosity pieces are misses at 5 m.** The backshell (a 12 px bright ring with a dark centre) has no
  candidate within 20 px; the nearest is 28.6 m away. The descent stage mark is a 40 m dark fan and the
  nearest dark candidate is 38.4 m from the recorded point. Whether a 5 m radius is the right test for a
  mark that size is a question for the person who owns the thresholds; see the proposal below.
- **The crash scar** (20 by 12 m dark patch) is found by the dark branch 17.7 px off at rank 51685, among
  35212 dark candidates on that strip. The dark branch is not a detector of impact marks at this calibration.
- **Schiaparelli ground is miscalibrated**, as the baseline report warned: the 2 per km2 operating threshold
  leaves 11 and 16 candidates per km2 on its two strips, against 0.01 on Phoenix and Viking 1. A single
  threshold does not mean the same thing on every strip yet.
- **The sheets were fair to the person filling the key.** Local ranks within 1.5 km put 7 of 13 pieces in
  the top 50, which is what the contact sheets show (the four hits at 1, 1, 1, 4; the Phoenix backshell at
  2; the Curiosity heat shield at 30; the Phoenix lander at 41). The six others were placed from registered
  caption images or grids, not from the lists.

## What I decided and why

- Ran the person-owned scoring script as it is and reported its output unchanged. Did not touch
  `scripts/score.py`, `landers/score.py`, `controls/thresholds.json` or `controls/tuning.json`.
- Put the diagnostics in `experiments/first_score_diag.py`, not beside the scoring script, so there is one
  number and one script that produces it. The diagnostics read the same three files and write a second
  results file; every number above is in one of the two.
- Did not commit the two results files: `out/` is ignored and they carry observation ids, which the leak
  check allows only under `docs/reports/`. The score script's full output is reproduced above and the
  command reruns in two seconds.
- Wrote `docs/proposals/scoring-v1.md` for the person who owns the scoring script: one candidate should
  match at most one piece, and the two marks (crash scar, descent stage) should be reported apart from the
  hardware. Proposed, not applied.
- Did not change the baseline or rerun anything through the detector. Baseline v1 stays frozen.

## What I would do next

Item 5 is done; item 6 (shape features into the score) is the next open item, and this score says where
to point it: the bright branch's calibration against real bright pieces, the shadow pairing that fires on
nothing, and the dark branches that find hard metal only among thousands of look-alikes. The thirteen
recorded pieces are also the material for item 7's transplant injection. Any change is
scored against the same key with the same script, and the number to beat is 3 of 13 at 708 per km2.
