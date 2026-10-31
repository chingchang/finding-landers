# Item 16: the two-sided test for dark candidates does not meet the rule and is not adopted

The test ties frozen-v1 at N = 20 on both boards: key 8 of 32 and transplant 15 of 128. A tie does not beat, so nothing
changes. No recorded piece leaves the top 20, and none is lifted by the test either: no recorded piece's dark candidate
passes it. The boards hold no known dust-covered piece, so this does not show the test is useless for dust-covered hardware.
It shows only that on these boards it costs little and adds nothing at the top of the list. The protocol was committed
before any measurement (`docs/proposals/darkrelief-v1-protocol.md`, commit 89a2f94).

Numbers are from `docs/reports/2026-10-30-darkrelief/summary.json`, a copy of `out/darkrelief/results.json`, and
`docs/reports/2026-10-30-darkrelief/why.json`. Everything is on tuning sites, and all four sites sealed for frozen-v1
(perseverance, insight, zhurong, beagle2) are **not blind** here. No paid call was made. Frozen-v1 reproduces item 13's
numbers on both boards at every N; the script stops if it does not.

## The test

The detector's recorded `two_sided` starts its bands at the equivalent radius from the centroid, so on a patch stretched
along the sun axis, which is what a cast shadow is, it reads the patch itself. The new measurement starts beyond the patch's
own edges. It asks for the sign of the relief: something lit on the sun side of the darkness (an object's lit face) and not
on the anti-sun side (where a depression has its lit wall), nothing dark on the sun side, a length that reads as a 0.5 to 3 m
object, and a width of at most 10 m. The one fitted number is a threshold per branch, set so that 0.001 of each branch's
listed candidates pass, with no truth involved. The gain is the measured -log10 of that fraction, as for every rule.

The fit on all tuning strips gives T = 6.03 for `dark` (135 of 134,720, gain 2.999) and T = 5.65 for `dark_compact` (376 of
375,433, gain 2.999).

## The result

Pieces in the top N. "False alarms allowed" applies to the transplant board. The test column is leave one site out.

| N | key, frozen-v1 | key, test | transplant, frozen-v1 | transplant, test | false alarms allowed |
|---|---|---|---|---|---|
| 10 | 8 of 32 | 8 | 15 of 128 | 15 | 1 |
| **20** | **8** | **8** | **15** | **15** | **3** |
| 50 | 10 | 9 | 25 | 25 | 8 |
| 100 | 11 | 11 | 34 | 34 | 16 |
| 250 | 13 | 13 | 47 | 47 | 41 |
| old board rate, 2 per km2 | | | 45 | 45 | 33 |

| Rule | Result |
|---|---|
| Key recall@20 beats frozen-v1 | no, 8 against 8 |
| Transplant recall@20 beats frozen-v1 | no, 15 against 15 |
| No recorded piece leaves the top 20 | yes, none |

- **95 percent intervals at N = 20 (Wilson).** Key 0.133 to 0.421 and transplant 0.072 to 0.184, the same in both arms because
  the counts are the same. The transplant interval is too narrow, because copies of one piece are not independent.
- **Spread over the ten sites at N = 20.** Key: mean 0.308, sd 0.338. Transplant: mean 0.118, sd 0.092. Both arms are the same.
- **By kind at N = 20, both arms.** Key: hardware 7, fabric 1, marks 0. Transplant: hardware 12 of 92, fabric 3 of 24, marks 0
  of 12.
- **Sham plantings with a detection at the N = 20 threshold:** 0 of 128 for frozen-v1 and for the whole fit.

## Why it moved nothing

These readings came after the result and decide nothing (`why.json`, from `experiments/darkrelief_why.py`).

**No piece's dark candidate reaches T.** Thirteen dark candidates lie within a recorded piece's match radius; none gets the
gain. Seven fail a fixed condition, all for darkness on the sun side (one also on height). The other six pass the fixed
conditions, and their dipoles are all under T, the highest being 4.98.

| dark candidate | branch | dipole | sun side, darkest z | height, m | fails | share of its strip and branch at or above |
|---|---|---|---|---|---|---|
| spirit backshell | dark_compact | 29.46 | -2.2 | 0.4 | sun side, height | 0.00004 |
| viking1 lander | dark_compact | 4.98 | -1.39 | 0.98 | | 0.00089 |
| zhurong backshell (not blind) | dark | 3.46 | 0.09 | 2.33 | | 0.05892 |
| phoenix heat shield | dark_compact | 1.49 | -0.91 | 0.86 | | 0.08895 |
| phoenix heat shield | dark | 1.29 | -3.1 | 1.47 | sun side | 0.05827 |
| insight lander (not blind) | dark_compact | 1.27 | -2.33 | 0.72 | sun side | 0.287 |
| phoenix lander | dark | 1.0 | -1.3 | 1.72 | | 0.11518 |
| zhurong lander (not blind) | dark_compact | 0.93 | -2.08 | 1.78 | sun side | 0.42077 |
| schiaparelli heat shield | dark | 0.53 | -2.36 | 2.16 | sun side | 0.0198 |
| phoenix backshell | dark | 0.44 | -0.45 | 2.16 | | 0.30352 |
| insight lander (not blind) | dark | 0.31 | -2.19 | 2.87 | sun side | 0.35627 |
| schiaparelli crash scar | dark | -1.0 | -2.28 | 2.01 | sun side | 0.55538 |
| insight heat shield (not blind) | dark_compact | -1.17 | -0.43 | 1.11 | | 0.73652 |

**The sign is mostly right on the pieces, and that is not enough.** Eleven of the thirteen dipoles are positive, as an object
would give, but most strips lean that way anyway. On `dark_compact`, 12 of 14 strips have more positive than negative dipoles
(`per_strip`). The two exceptions are both Schiaparelli strips (ESP_048041_1780: 20,021 positive, 54,959 negative), which
could mean mostly depressions there. I have not looked at them. A rock is relief too, and the test cannot tell it from
hardware.

**One threshold in z does not suit every ground.** Under the whole fit no candidate passes on the two Phoenix strips, the only
polar ground among the tuning sites, or on Pathfinder, Curiosity, one Beagle 2 strip (ESP_039308_1915, not blind) or the second
Schiaparelli strip (ESP_073625_1780). The passers cluster on a few strips: `dark_compact` passes at 0.00837 on the InSight strip and 0.00528 on the Zhurong strip, against the
target 0.001. On the InSight strip 18 of the top 20 are passers (`top_20` in `why.json`), and none of them is a recorded
piece's dark candidate, since none of those passes. This is the same property of the ground that had `tile_top` withdrawn. A threshold per strip would be a new
design, and I did not try it. On the table above it could not help much: the only two pieces inside the top 0.1 percent of
their own strip's dipoles are viking1 lander and spirit backshell, and spirit backshell fails the fixed conditions anyway.

**On the planted tiles it barely acts.** Of 4,731 dark detections, 4 pass the whole fit, and 3 of those are on a planted piece
(spirit backshell twice, perseverance rover once). Each of those pieces already has a shadow detection above the score the
gain gives. The dark candidate is second in line, so the gain changes nothing.

**What it costs.** Passers push pieces down on the rougher strips. Under the folds: perseverance parachute 25 to 35, and
backshell 44 to 57 (both not blind), spirit parachute 116 to 184, insight lander 469 to 566 (not blind), spirit lander 441 to
582. At N = 50 the key falls from 10 to 9.

## Reported beside, deciding nothing

| arm | key at 10, 20, 50, 100, 250 | transplant at 10, 20, 50, 100, 250, 2 per km2 | pieces dropped |
|---|---|---|---|
| frozen-v1 | 8, 8, 10, 11, 13 | 15, 15, 25, 34, 47, 45 | |
| test, leave one site out (primary) | 8, 8, 9, 11, 13 | 15, 15, 25, 34, 47, 45 | 0 |
| test, whole fit | 8, 8, 9, 11, 13 | 15, 15, 25, 34, 46, 45 | 0 |
| p = 0.0005 | 8, 8, 9, 11, 13 | 15, 15, 25, 34, 47, 45 | 0 |
| p = 0.002 | 8, 8, 9, 10, 13 | 15, 15, 25, 34, 46, 45 | 0 |
| placebo, sun on the wrong side | 8, 8, 10, 11, 13 | 15, 15, 25, 34, 47, 45 | 0 |
| recorded `two_sided` and height | 5, 8, 11, 12, 14 | 15, 15, 24, 34, 46, 44 | 1 |
| `dark_compact` only | 8, 8, 9, 11, 13 | 15, 15, 25, 34, 46, 45 | 0 |
| `dark` only | 8, 8, 10, 11, 13 | 15, 15, 25, 34, 47, 45 | 0 |

- **The placebo is as good as the test, and better at N = 50 on the key.** So these boards give no sign that the physics is
  doing anything. They can hardly show it either way, because the test moves so little.
- **The recorded feature does move pieces, both ways.** It takes insight lander (not blind) from 469 to 16, and it reads higher
  than frozen-v1 at N = 50, 100 and 250 on the key. It also takes pathfinder backshell from 4 to 30 and drops the key to 5 at
  N = 10, and at N = 20 it ties. It has no standing under the rule and I am not proposing it. Item 8 tried the same features on `dark` at a
  threshold of 3.0 and reverted it (docs/experiments.md).
- **The folds agree with the whole fit.** T ranges over 5.11 to 7.06 for `dark` and 5.16 to 6.13 for `dark_compact`, the
  highest in each when Schiaparelli is left out, whose strips hold many candidates that rarely pass.
- **No-texture target strips** at N = 20, 43 plantings: 8 in both arms. Textured, 85 plantings: 7 in both.

## What I decided and why

- **A new measurement as the primary, the recorded feature as a comparison.** Item 8 already tried the recorded feature on the
  `dark` branch, and the patch reading itself explains why it could not work on a shadow. Running only that would have spent the
  item on a known answer.
- **Measure on the frozen lists, with the flag off by default.** The detector reran over the 14 tuning strips and the 46 tiles
  with the features on, and every strip and every tile agreed with frozen-v1's list and item 13's records. `DetectorConfig`'s
  default leaves frozen-v1 as it was, and a test pins that the flag moves no candidate.
- **Nothing to propose.** There is no question for the person from this item and no rules file. The code stays behind its flag,
  unused.

## Things that went differently from plan

- **The measure pass hit the two-hour limit once.** It wrote each strip as it landed; 12 of 14 were done and the resume took the
  last two.
- **The rerun's flag reads dirty, and the file behind it is not mine.** The results reran at 6245637 (the first at 89a2f94) with
  everything identical apart from `git`. Both record `dirty: true`. The one tracked file changed outside this item's commits is
  `docs/reports/ledgers.json`, at 18:39 local while my measure pass ran: reformatted, with an entry added for item 14 with `out/deep14/ledger.json` marked live. No file of
  this item touches it, and that ledger file does not exist on this checkout, so nothing there shows a paid call. I have left the
  change uncommitted and do not know what wrote it. Whoever owns item 14 should check it.
- **Nobody has looked at these on the pixels.** I did not open any crop. The readings above of lit faces, depressions and rough
  ground are what the numbers would mean if the geometry holds, not something seen.

Green: `uv run pytest -q` and `scripts/leakcheck.sh`. `uv run ruff check` flags long lines in the new files, as it does in
`scripts/halfcal.py` and `scripts/rerank.py`, and nothing else.

## What I would do next

Leave item 16 closed and keep v2's order as the combined list from item 14. If dust-covered hardware is to be measured at all,
the honest board would be planted copies dimmed toward the ground's albedo, which this project does not have yet, and it would
come after the blind run, not before.

## Commands

    uv run --env-file out/landers.env scripts/darkrelief.py tiles
    uv run --env-file out/landers.env scripts/darkrelief.py measure --jobs 3
    uv run --env-file out/landers.env scripts/darkrelief.py score --no-texture PSP_004336_1035 PSP_004402_1030
    uv run experiments/darkrelief_summary.py
    uv run --env-file out/landers.env experiments/darkrelief_why.py

These need item 15's `out/halfcal/pop` and `out/halfcal/t10`, from `scripts/halfcal.py pop` and `redetect`.

Credit for all images: NASA/JPL/University of Arizona.
