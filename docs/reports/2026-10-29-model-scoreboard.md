# Report: the model-layer scoreboard on the tuning sites (2026-10-29)

Plan item 9c, branch `claude/model-layer`. A person asked for this run on 10-29 and approved the spend (plan
item 9c). `MODEL_API_KEY` and `LANDERS_REAL_CALLS=1` were both in the environment, and the loop prompt named
the item. Caps came from `out/caps.env`: `LANDERS_CAP_SAM=200`, `LANDERS_CAP_WONDER=260`,
`LANDERS_CAP_SPARK=120`.

Every number below is copied from `docs/reports/2026-10-29-model-scoreboard/summary.txt`, which
`experiments/scoreboard_summary.py` prints from the published records in that directory. The same numbers,
per id, are in `summary.json` there. The ledger, every per-stage record, each review's tool log and the
recordings are committed in that directory. `PUBLISHED.json` lists them, and its `withheld` entry lists
seven files that are not committed (see "Withheld files").

## Question and answer

What do SAM, the Wonder votes and the Spark review add on top of the frozen detector, and do they ever
lower a real piece?

- **No recorded piece was lowered.** 8 top-20 ids sit on recorded pieces. They cover the 8 pieces that
  `scripts/score.py` places in the top 20, and one of those ids is also inside the Schiaparelli
  parachute's radius. Every one of them ends at "needs second look", as it started.
- **34 of 152 false alarms were lowered to "likely natural"**: 31 by the vote rule and 3 by the review,
  none by both. 44 were kept by a review verdict, 12 were kept by the votes with no verdict recorded, and
  62 were not assessed by any stage.
- **Cost:** $6.7124 by the ledger, or $0.1974 per false alarm lowered. That covers 161 SAM images, 260
  Wonder calls (27 refused at the cap) and 89 Spark turns.
- **SAM by itself lowered nothing,** by design: its tests are evidence for the reviewer. On the 152 false
  alarms it gave `sam_edge` 6 fail, 12 pass and 134 unsure, and `sam_size` 18 pass and 134 unsure. On the 8
  piece ids most tests were unsure (`sam_size` 7 unsure, 1 pass).

The scoreboard says the vote rule does the useful work, and that no stage costs a real piece on these
strips. It also says the run is incomplete. More than a third of the false alarms (62 of 152) were never
assessed, and two strips got no votes at all. The next section explains why.

## What ran

Input: `out/shape_v3/candidates_v03_features.json` from the data worktree
(`repo-overview-plan-e248f3`), with `landers/shape_v3.json` applied offline by
`experiments/scoreboard_inputs.py` (the same `apply_rules_json` that `scripts/rescore.py` and the tuning
judge use), cut to the top 200 per strip. Scoring that cut with `uv run scripts/score.py
out/scoreboard/inputs/candidates_frozen_v1.json` gives recall@20 8 of 18 and hardware 7 of 12. That is
the reference side recorded for the freeze in `docs/reports/2026-10-29-tuning-loop-3.md`, so this is the
list frozen-v1 scores.

For each of the eight strips, `experiments/scoreboard_run.py` ran three stages:

1. three Wonder votes on each of the top 10, with a reference crop from the Spirit strip
   (`--reference ESP_025815_1655`), or from the Curiosity strip for the Spirit strip itself
   (`--reference-for-reference ESP_030313_1755`), as in item 9b;
2. SAM on the top 20;
3. one Spark review of the top 20, with `MAX_TURNS` 12 unchanged.

All three stages shared one ledger in `out/scoreboard/`. A dry run of all eight strips came first
(`--backend dry-run --out-dir out/scoreboard_dry`, 425 requests written). I searched its request texts
for observation ids, mission and site names, dates and file names. The only hit was the generic piece-kind
list in the thresholds the reviewer reads (lander, backshell...), which item 9b also sent. The detector,
thresholds and prompts are unchanged.

## Per strip (from summary.txt)

| strip | review | votes on | on piece | FA lowered (votes / review) | FA kept by review | FA kept by votes only | FA unassessed |
|---|---|---|---|---|---|---|---|
| ESP_030313_1755 | turn cap, 12 turns, 5 verdicts | 10 | 2 | 6 (4 / 2) | 0 | 2 | 10 |
| ESP_025815_1655 | turn cap, 12 turns, 0 verdicts | 10 | 1 | 3 (3 / 0) | 0 | 6 | 10 |
| ESP_022038_1995 | turn cap, 12 turns, 2 verdicts | 10 | 1 | 4 (4 / 0) | 1 | 4 | 10 |
| ESP_048041_1780 | turn cap, 12 turns, 8 verdicts | 10 | 1 | 9 (9 / 0) | 0 | 0 | 10 |
| ESP_073625_1780 | turn cap, 12 turns, 0 verdicts | 10 | 0 | 10 (10 / 0) | 0 | 0 | 10 |
| ESP_017716_2485 | turn cap, 12 turns, 8 verdicts | 3 | 2 | 2 (1 / 1) | 4 | 0 | 12 |
| ESP_053451_2485 | final answer, 10 turns, 20 verdicts | 0 | 0 | 0 | 20 | 0 | 0 |
| ESP_046170_2025 | final answer, 7 turns, 20 verdicts | 0 | 1 | 0 | 19 | 0 | 0 |

The recorded pieces in the top 20, with what each stage said:

- Curiosity parachute, rank 3: votes hardware 0.80, 0.86, 0.72. The review kept it, citing the votes and
  the size and edge tests on a zoom pass it ordered.
- Curiosity backshell, rank 8: votes hardware 0.85, natural 0.78, hardware 0.72; SAM passed size, shape
  and edge. The review ordered three more votes, which came back **natural 0.72, 0.65, 0.65**. The rule
  (two natural at 0.7 or more, none hardware) kept it by one vote. No verdict was recorded.
- Spirit backshell, rank 1: votes hardware 0.70, 0.68, natural 0.65. No verdict was recorded.
- Pathfinder backshell, rank 4: votes unsure 0.60, unsure 0.60, hardware 0.82. More votes: unsure 0.55,
  natural 0.72, unsure 0.55. No verdict was recorded.
- Schiaparelli backshell, rank 8 (the id is also within the parachute's radius): votes natural 0.62,
  hardware 0.88, 0.78. More votes: hardware 0.82, 0.80, 0.88. The review kept it.
- Phoenix backshell, rank 2: votes hardware 0.75, natural 0.65, natural 0.65. The review kept it.
- Phoenix heat shield, rank 5: no votes (cap). The review kept it, citing the unsure tests.
- Viking 1 lander, rank 3: no votes (cap). The review kept it, citing the unsure tests and an
  edge-touching mask.

## What I decided and why

- **The run was asked for.** The plan records the person's request and approval for this item, both env
  gates were set by the person, and the loop named 9c. The caps were the plan's own.
- **The Wonder cap ran out and I did not raise it.** The plan sized 260 Wonder calls as 240 for the votes
  plus a margin. The reviews ordered 33 more-vote checks (99 calls), 16 of them on the Pathfinder strip
  alone. The last Phoenix strip got votes on 3 ids, and the second Phoenix strip and the Viking strip got
  none. The caps are a person's. The shortfall is reported as unassessed, not made up with a second run.
- **The reviews ran out of turns.** Six of eight reviews hit the 12-turn cap. Two recorded no verdict at
  all, because they spent their turns fetching records and ordering checks. The two that finished were the
  two with no votes to weigh. Of the 33 more-vote checks, 20 came back with the rule saying "likely
  natural", and none of those 20 ids was then lowered: the review never reached a verdict for them. The
  item forbids changing prompts or limits here, so this goes to the next tag.
- **Withheld files.** One SAM measurement on the Viking strip has a mask area equal to a sealed site's
  published coordinate, and `scripts/leakcheck.sh` matches any bare number equal to one. That number then
  appears in six Spark recordings of that strip's review. The numbers are never edited, so
  `experiments/withhold.py` left those seven files out of the commit, kept them under `out/scoreboard/`, and
  listed them in `PUBLISHED.json`. The summary reads them from there. Replaying the Viking strip's review
  from the committed recordings is therefore incomplete.
- **The ledger may overstate cost.** A replayed request still counts against the cap. No stage was
  replayed in this run, so the ledger equals what was sent. As item 9b noted, the Wonder token count may
  still be an undercount compared with the bill.

## What to check by eye

The 31 vote-lowered false alarms are listed per id in `summary.json` (status "lowered", `lowered_by`
votes), with their positions in `out/scoreboard/manifest_<strip>.json`. On ESP_073625_1780 and
ESP_048041_1780 the votes lowered 10 of 10 and 9 of 10. A person should look at a few from each of those
strips to see whether the vote rule is right or just harsh on that ground. A rule that lowers everything
on a strip would also lower a piece there.

## What I would do next (for a later tag, not this item)

- **Review loop:** ask for every verdict in one turn after the fetches, or count checks against a separate
  budget from verdicts. As it stands the reviewer's most expensive actions produce no grade.
- **Wonder budget per strip:** reserve 30 calls per strip for the votes before any check may spend, so a
  review on one strip cannot starve the votes of a later one.
- **The vote rule:** do not move to a mean rule. Item 9b suggested lowering at a mean of 0.66 natural. The
  Curiosity backshell's second draw (natural 0.72, 0.65, 0.65) would have been lowered by it.
- **Rerun the three under-voted strips** (votes only, about 81 Wonder calls) when a person asks, so all
  eight strips are scored the same way.
