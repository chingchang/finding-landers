# Item 14a: item 14 published, and neither vote ordering holds up on the transplant board

**My recommendation for 16a's switch: no vote ordering, and no lowering by the vote rule. The v2 list stays the combined list.**
The oracle and the person decide. On the key, ordering (a) and ordering (b) both reach 19 of 32 at 20, against 16 on the combined
list, and no recorded piece leaves the top 20. On the transplant board, the stand-in for polar ground, (a) falls from 21 to 14 of
128 at N20 and (b) falls to 20. Under the test I wrote before scoring them, a key gain with a transplant loss is not a gain.

**Two figures in the plan need correcting.** History stays, so I have not edited the Decisions entry of 10-31 07:00.

- **"Lowered 34 of 128 planted pieces" is not what the records show.** 128 is the number of planted pieces and, separately, the
  number of detections voted on. The rule lowered 34 detections of those 128. 12 of the 34 sit within a planted piece's match
  radius, and those 12 cover 9 of the 128 planted pieces. The other 22 sit on no planted piece.
- **"Four recorded pieces" lowered by Spark is four rows on three pieces.** Two rows are the same Phoenix heat shield. That is why
  the key falls by 3 at 20, from 18 to 15.

Everything here is on tuning sites, and the four sites sealed for frozen-v1 are **not blind**. Both orderings and the combined list
were chosen after seeing results, so only item 17's blind run can judge them. No model was called and no heldout strip was opened.

All numbers are from `docs/reports/2026-10-31-vote-orderings/`: `orderings.json`, `lowered.json`, and `tables.md`, which is generated
from them and holds every list and row in full. The orderings were committed in `docs/proposals/vote-order-v1.md` (commit eae1215)
before the script that scores them existed. By then I had seen item 14's summary, but nothing about these two orderings.

## The curves

Each cell is the number on the list, with the 95 percent Wilson interval in percent.

**Key, of 32:**

| list | 10 | 20 | 50 | 100 | 250 |
|---|---|---|---|---|---|
| frozen-v1 | 8 (13-42) | 8 (13-42) | 10 (18-49) | 11 (20-52) | 13 (26-58) |
| combined | 12 (23-55) | 16 (34-66) | 18 (39-72) | 19 (42-74) | 19 (42-74) |
| combined + vote rule | 13 (26-58) | 18 (39-72) | 19 (42-74) | 19 (42-74) | 20 (45-77) |
| (a) | 17 (36-69) | 19 (42-74) | 19 (42-74) | 19 (42-74) | 19 (42-74) |
| (a) + vote rule | 17 (36-69) | 19 (42-74) | 19 (42-74) | 19 (42-74) | 20 (45-77) |
| (b) | 16 (34-66) | 19 (42-74) | 19 (42-74) | 19 (42-74) | 19 (42-74) |

**Transplant, of 128.** The cut here is a false-alarm allowance over the whole pool (N10 1, N20 3, N50 8, N100 16, N250 41, board
rate 33), set from the same rate per km2 as the key's N:

| list | N10 | N20 | N50 | N100 | N250 | board rate |
|---|---|---|---|---|---|---|
| frozen-v1 | 15 (7-18) | 15 (7-18) | 25 (14-27) | 34 (20-35) | 47 (29-45) | 45 (27-44) |
| combined | 11 (5-15) | 21 (11-24) | 31 (18-32) | 36 (21-36) | 56 (36-52) | 53 (33-50) |
| combined + vote rule | 11 (5-15) | 20 (10-23) | 31 (18-32) | 41 (25-40) | 53 (33-50) | 53 (33-50) |
| (a) | 8 (3-12) | 14 (7-18) | 31 (18-32) | 39 (23-39) | 56 (36-52) | 53 (33-50) |
| (a) + vote rule | 8 (3-12) | 14 (7-18) | 32 (18-33) | 41 (25-40) | 53 (33-50) | 53 (33-50) |
| (b) | 11 (5-15) | 20 (10-23) | 28 (16-30) | 42 (25-41) | 51 (32-48) | 50 (31-48) |

How far these can be read:

- **Every key gain sits inside the intervals.** 16 of 32 is 34 to 66 percent and 19 of 32 is 42 to 74.
- **The intervals are too narrow, if anything.** Wilson treats pieces as independent. Key pieces share strips and sites, and
  transplant pieces are repeated copies of the same sources.
- **The key cannot go past 19 at 20.** 11 pieces are not on the combined list, and Phoenix's lander (274) and InSight's lander
  (367) sit below the voted depth, so (a) and (b) are at that ceiling.
- **The three rows item 14 published come out the same here.** The script stops if frozen-v1, combined or combined + vote rule
  differ from its `summary.json`.

## Pieces that cross the top 20, against the combined list

**Key.** No recorded piece leaves the top 20 on the vote rule, (a), (a) + vote rule or (b).

| list | pieces coming in (rank on combined, then here) |
|---|---|
| combined + vote rule | Zhurong backshell (24, 13), Zhurong heat shield (33, 19) |
| (a), also (a) + vote rule | Perseverance backshell (66, 7), Zhurong backshell (24, 4), Zhurong heat shield (33, 6) |
| (b) | Perseverance backshell (66, 13), Zhurong backshell (24, 7), Zhurong heat shield (33, 9) |

Zhurong and Perseverance were both sealed for frozen-v1, so these three moves are not blind.

**Transplant at N20**, by planted piece, its size and its target strip:

- **Combined + vote rule: 2 out, 1 in.**
  - Out: Beagle 2 lander 1 m on `ESP_013500_1035`; Pathfinder backshell 2.6 m on `ESP_057965_1035`.
  - In: Spirit lander 3 m on `ESP_013500_1035`.
- **(a) and (a) + vote rule, the same pieces: 13 out, 6 in.**
  - Out:
    - Spirit backshell 2.6 m on `ESP_013078_1030`
    - Zhurong heat shield 3.4 m on `ESP_013078_1030`
    - Beagle 2 lander 1 m on `ESP_013500_1035`
    - Perseverance descent stage 20 m on `ESP_048734_1035`
    - Curiosity backshell 3 m on `ESP_048734_1035`
    - two Pathfinder backshells 2.6 m on `ESP_057965_1035`
    - Curiosity backshell 3 m on `PSP_004336_1035`
    - on `PSP_004402_1030`: Schiaparelli parachute 12 m, Perseverance backshell 4.5 m, Viking 1 lander 3 m and two Curiosity
      backshells 3 m
  - In: Zhurong heat shield 3.4 m on `ESP_013078_1030`; on `ESP_013500_1035`, Spirit backshell 2.6 m, Spirit lander 3 m and
    Zhurong parachute 15 m; Curiosity parachute 16 m on `ESP_048734_1035`; Curiosity heat shield 4.5 m on `PSP_004402_1030`.
- **(b): 7 out, 6 in.**
  - Out: Beagle 2 lander 1 m on `ESP_013500_1035`; Perseverance descent stage 20 m on `ESP_048734_1035`; two Pathfinder backshells
    2.6 m on `ESP_057965_1035`; Curiosity backshell 3 m on `PSP_004336_1035`; Curiosity backshell 3 m and Viking 1 lander 3 m on
    `PSP_004402_1030`.
  - In: the same six as (a).

## Why the two boards disagree

The votes separate real pieces from the rest far better on native crops than on planted ones. First votes by what the row is:

| board | row | hardware | natural | unsure |
|---|---|---|---|---|
| key lists | on a recorded piece | 16 | 4 | 1 |
| key lists | anything else | 65 | 1,004 | 110 |
| transplant | on a planted piece | 27 | 36 | 17 |
| transplant | anything else | 7 | 36 | 5 |

So hardware is the first vote on 16 of 21 rows on recorded pieces, and on 27 of 80 rows on planted pieces. These tables do not
separate the possible reasons. The paste may change how a piece looks, the polar ground may hide it, or the key pieces that reach
the top 100 may just be easy ones. The recognition probe does not account for the key's result: Wonder claimed to recognise none
of 18 views (`docs/reports/2026-10-30-deep-pass/run/probe_*.json`), though a probe that asks is not proof that a crop never helped.

The N20 cut is also harsh on promotion. It allows 3 false alarms over the pool, so a few hardware votes on false alarms use it up. I
read that as the mechanism behind (a)'s fall, but did not trace it row by row.

**A check I added after seeing the board, not in the proposal.** A fold's top 100 reaches much deeper by false-alarm rate than a
strip's top 100, because the pool is only 16.5 km2. So I reran both with votes counting only down to the N100 rate, which is a depth
of 56 to 66 per fold. (a) gives 16 at N20 and (b) gives 21, but (b) then falls to 24 at N50 against the combined list's 31. The depth
mismatch explains part of the loss, and neither ordering comes out clean.

**(b) depends on its factor, and the factor of 4 has no measurement behind it.** Factor 2 gives key 18 and transplant 21 at 20, with
26 at N50. Factor 8 gives key 18 and transplant 15, and on the key it pushes Spirit's parachute out of the top 20 (5 to 25). These
rows are sensitivity only.

## What was lowered on planted pieces

The crops are in `lowered_planted.png`, one stretch per sheet, numbered as below, and cut from the planted search tiles of
`out/rerank/t10`. The last column is my own reading of the sheet by eye. "Lost" means the piece was on the combined list at some
cut and is on the vote rule's list at none.

| sheet | planted piece | size, m | branch | area, px | px from the piece's centre | effect of the rule | what the crop shows |
|---|---|---|---|---|---|---|---|
| 1 | Beagle 2 lander | 1 | bright | 8 | 2.9 | lost | small bright speck on streaked ground |
| 2 | Beagle 2 lander | 1 | bright | 8 | 3.9 | lost, was at N20 | one bright point on dark ground |
| 4 | Pathfinder backshell | 2.6 | bright | 19 | 1.1 | lost, was at N20 | compact bright blob on dark ground |
| 9, 10 | Phoenix lander | 2.5 | dark_compact, dark | 79, 86 | 6.1 | lost | dark compact patch inside a mottled bright surround; one object, two rows |
| 5, 7 | Schiaparelli crash scar | 20 | dark_compact, dark | 30, 50 | 17.5, 17.6 | lost | diffuse dark spot with faint rays; one object, two rows |
| 11 | Perseverance descent stage | 20 | bright | 15 | 55.8 | lost | bright patch off the piece's centre |
| 6 | Phoenix backshell | 2.6 | dark | 94 | 7.3 | not lost; at N50 now, N100 before | dark patch with a small bright spot at its edge |
| 8 | Zhurong lander | 4 | dark_compact | 94 | 6.1 | not lost; also at board rate now | dark oval with a brighter rim on one side |
| 3, 12 | Perseverance descent stage | 20 | bright | 7, 9 | 57.6, 30.8 | no longer at N100, still at N250 | bright specks off the piece's centre |

- **Six of the 9 pieces are lost at every cut.** Three more stay on the list, because another detection covers them or because
  clearing false alarms lets them in earlier.
- **Six of the 9 are lander bodies or backshells of 1 to 4 m,** the sizes the search is looking for.
- **Sheets 3, 11 and 12 are probably not the planted piece.** They sit 31 to 58 px from the centre of a 20 m mark matched at 80 px,
  so they count on the board but may be other features inside the radius.
- **The 22 lowered detections on no planted piece** are listed in `tables.md`. None sits on a sham cut: 20 of all 8,183 detections
  are on a sham, and none of the 128 voted. So no vote here tested a paste seam alone. Sheets 13, 14 and 17 show the same bright
  crescent object, so those 22 are not 22 separate things.

## What Spark lowered on recorded pieces

| strip | piece | rank on combined | first vote | Spark's reason |
|---|---|---|---|---|
| `ESP_017716_2485` | Phoenix heat shield | 8 | natural 0.68 | Advisory vote describes diffuse dark blob merging into terrain consistent with rock and shadow. |
| `ESP_017716_2485` | Phoenix heat shield, second row | 11 | natural 0.62 | Advisory vote describes amorphous dark oval matching rock-shadow pairs with no geometric outline. |
| `ESP_025815_1655` | Spirit parachute | 5 | natural 0.65 | Lowers toward likely natural because the vote describes an irregular soft-edged patch with no cast shadow consistent with natural exposure. |
| `ESP_022038_1995` | Pathfinder backshell | 3 | natural 0.65 | Advisory vote reports natural with fuzzy irregular spot and similar speckles across terrain, supporting a lower grade. |

Every one of these first votes is under 0.70, so the vote rule had kept all four. Spark lowered them citing that same vote and no
new measurement; the parachute verdict adds only the branch. This supports the 10-31 07:00 decision to keep the review out of v2.

## What I decided and why

- **Recommendation: no ordering and no lowering in 16a's switch.** (a) fails plainly on transplant. (b) and the vote rule each lose 1
  at N20, within the noise, but the rule loses small lander-sized planted pieces at every cut, and (b)'s other moves (N100 +6, N50
  -3, N250 -5) have no consistent direction and shift with an unmeasured factor. The key gains are real rows, but they sit inside
  the intervals and rest on sites that are not blind.
- **One band for (a), the whole voted top 100.** A band ending at a reported cut could not move a piece across that cut, so the
  curve would look unchanged whatever the votes said.
- **(a) applied to the combined list, plus (a) + vote rule as an extra row,** because the plan did not say which base it meant, and
  this measures each change once.
- **On transplant, a vote counts for (a) and (b) only inside that fold's own top 100,** for the same depth as the key. The
  combined + vote rule row keeps item 14's published calculation, which applies a lowering in every fold.
- **The line in CLAUDE.md for the person.** "A model's opinion can lower a result, never raise it" speaks of grades. (a) and (b)
  change no grade, but they do lift a position on a list a person reads from the top. If either is ever adopted, that needs the
  person's reading of the line. My recommendation avoids the question.

## Things that went differently from plan

- **I resolved a merge conflict rather than committing it as work in progress.** The session started inside an unfinished merge of
  main, with a conflict in `docs/plan.md`. Committing it as told would have committed the conflict markers, so I kept both sides:
  16a's done status and main's new 16b.
- **I added rows nobody asked for:** (a) + vote rule, factors 2 and 8, and the N100-rate check. Each is labelled, and none is a
  further ordering to choose from.
- **One heredoc was refused by the permission layer.** I made those edits with the Edit tool, and nothing was skipped.

## What I would do next

Item 16b, with the model stage off. Before item 17's search spends its roughly 35 USD on votes, decide what those votes are for: this
item gives them no job in the ranking, so they could at most be a column beside each candidate.

## Commands that made these numbers

    uv run experiments/deep14_summary.py --run out/deep14 --no-texture PSP_004336_1035 PSP_004402_1030
    uv run scripts/models_publish.py out/deep14 docs/reports/2026-10-30-deep-pass/run
    uv run experiments/vote_orderings.py --run out/deep14 --out docs/reports/2026-10-31-vote-orderings/orderings.json
    uv run experiments/vote_lowered.py --run out/deep14 --out-dir docs/reports/2026-10-31-vote-orderings
    uv run experiments/vote_tables.py --dir docs/reports/2026-10-31-vote-orderings --summary docs/reports/2026-10-30-deep-pass/summary.json

Credit for all images: NASA/JPL/University of Arizona.
