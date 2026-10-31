# Plan

How this file is used. The agent reads it at the start of every session, takes the first open item under
"Now", does it, marks it, and writes a report under docs/reports/. A person owns the order and the backlog;
ideas from conversations land here, not in chat. Nothing in this file is a result.

## Now (in order; the agent keeps the status)

1. [done] Baseline v1: the calibrated detector over all six tuning strips, saved under out/baseline_v1/
   with the commit hash. Never rerun after the key is filled. The first score against the key comes from it.
2. [done] Contact sheets for the key: top 50 candidates within 1.5 km of each refined position in
   controls/sites.json, numbered with line and sample, plus a suggestions file. The agent does not write
   tuning.json.
   Feedback (oracle, 10-28 16:40): three things make the sheets usable by eye. (a) Stretch each grid with one
   global stretch per grid, not per tile; a per-tile stretch saturates the top 0.1 percent of every tile, so
   brightness cannot be compared across tiles and the brightest object in the area does not stand out.
   (b) On polar ground every polygon edge is a bright streak with a dark trough beside it, so rank by the
   shadow side from the label (SUB_SOLAR_AZIMUTH), not by brightness alone: a bright compact blob with dark
   pixels on the anti-sun side only. (c) For Schiaparelli the published position is 600 m precision and the
   monitoring strips are centred about 1.2 km from it, so use a 3 km area around each strip's own centre.
   Feedback (oracle, 10-28 16:20): the baseline report names the tuning strips, as a reproducible report must,
   and scripts/leakcheck.sh flags every observation id outside its allowlist, so the two cannot both pass.
   Allow observation ids under docs/reports/ (reports are for people and must say which strip a number came
   from); keep the sealed-site name and coordinate rules everywhere, reports included.
2b. [done, see docs/reports/2026-10-28-contact-sheets-second-pass.md] Sheets, second pass, rebuilt from the baseline v1 lists without changing them: one global stretch
   per sheet and per grid (not per thumbnail); a second ranking beside the score, the two-sided shadow test
   from the label azimuth (dark on the anti-sun side, not dark on the sun side); for Schiaparelli a 3 km area
   around each strip's own centre; and scripts/leakcheck.sh allowing observation ids under docs/reports/
   only, with the sealed-site name and coordinate rules kept everywhere. Reports may then name strips.
3. [person] Key filled by a person from the sheets and grids, in a private copy. Copied to controls/tuning.json and
   committed only after item 1 is committed.
4. [done, see docs/reports/2026-10-28-first-score.md] First score: baseline v1 against the key. This is the blind number; report it as such.
   Scored with the key at 13 of 22 pieces; a person may rescore when more pieces are filled (same command,
   same baseline file). docs/proposals/scoring-v1.md waits for a person.
5. [done, see docs/reports/2026-10-28-persistence.md] Persistence: local registration (phase correlation on a 512 px window) between the two Schiaparelli
   dates and the two Phoenix dates; measured offsets in a report; a persistence branch that matches position
   only. Hard parts (lander, backshell, heat shield, fragments) must sit in the same place on both dates to
   reach "candidate". Sheets get a 50 m radius and are never marked "likely natural" for moving or vanishing.
   Absent on a later date is weak evidence (burial) and returns unsure, never fail.
6. [done, see docs/reports/2026-10-29-shape-rules.md] Shape features into the score, only where real pieces sit in the top few percent of that feature's
   false alarms on the same strip; each threshold recorded and versioned. Two-sided shadow test (dark on the
   anti-sun side and not dark on the sun side), shadow length consistent with a 1 to 3 m height, isolation.
   Features recorded (detector v0.2); three rules drafted blind and measured on the eight tuning strips; none
   meets the draft's bar, so none is in the score. The saturation rule (0.003 of false alarms, recall@20 0.31
   against 0.15 when rescored) waits for a person in docs/proposals/shape-rules-v1.md. The sheet branch keeps
   the v0.1 saturation mask; a fully saturated sheet is a question for item 7.
7. [done, see docs/reports/2026-10-29-transplant-injection.md] Transplant injection: cut each confirmed piece at full resolution from its tuning strip and plant it
   into MPL-strip tiles with matched incidence; score as injection. Nothing cut from, or planted into, a
   held-out site. This becomes the main scoreboard for tuning; the six real sites stay a constraint.
8. [done, see docs/reports/2026-10-29-tuning-loop-3.md] Tuning loop, third and last session, detector changes only, then the freeze. Two levers, each judged by
   scripts/tune.py on both boards against the shape_v3 reference (rerun the key pass and the transplant command
   once with shape_v3 to set it), each a fresh key pass and transplant run, kept only under the item 8 bar
   (hardware recall@20 and injection recall may not drop, no recorded piece leaves the top 20, rules re-measured
   and re-versioned after any detector change; proposals to docs/proposals/, adopted by a person):
   (a) Calibration per terrain. One calibrated threshold means 0.01 candidates per km2 on the Phoenix strips
   and 11 to 16 on Schiaparelli (docs/reports/2026-10-28-first-score.md). Fit the calibration so that a
   calibrated score means the same false-alarm rate on every strip: per strip from its own candidate
   population (the recorded pieces are a negligible fraction of it), or per terrain class if that is more
   stable under leave-one-site-out. Measure what it does to the Schiaparelli heat shield and crash scar
   (ranks 31,800 and 51,700 among that strip's dark candidates) and to the Phoenix pieces.
   (b) The fabric branch. Fabric is 1 of 4 on the key (the Schiaparelli parachute found only as a bright
   fragment at rank 760, Spirit's at 109, Pathfinder's not at all) and 10 of 24 on injection. Revisit the
   sheet branch's flatness test and its handling of saturated and dust-reddened canopies against the four
   recorded parachutes and the injected fabric; the earlier finding that saturated pixels as data broke the
   flatness test is in docs/experiments.md.
   Then stop: write the report, and leave the detector as it stands for the frozen tag. The earlier sessions
   are docs/reports/2026-10-29-tuning-loop.md and -2.md; their leftovers (second injection seed,
   leave-one-site-out on thresholds, sheet flatness threshold) fold into (b) or the backlog.
9. [done, see docs/reports/2026-10-28-model-layer.md] Model layer, built blind, no key and no network: read docs/models.md first. One interface for
   SAM 3.1, Muse Wonder and Muse Spark with a fake backend (deterministic) and a recorded backend; the
   ledger with hard caps and cost estimate; SAM box-prompt requests and mask parsing feeding the size and
   shape tests; the blind-crop builder (augmentations, reference crops, nothing identifying) and the Wonder
   vote with a strict schema; the recognition-probe harness; the Spark review loop with its five tools,
   keep or lower only, every verdict citing evidence; a dry-run mode that writes the requests it would
   send; the prompt leak test. Runs in its own worktree (branch claude/model-layer) and touches only
   landers/models/, scripts/models_*.py, their tests and docs; everything green with no network.
9b. [done, see docs/reports/2026-10-29-first-real-run.md] First real run, after MODEL_API_KEY is in the environment and a person asks: recognition probe on
   Curiosity and Phoenix first, then one tuning site, 20 SAM calls, 9 Wonder votes, one Spark review;
   ledger and tool log committed with the report; grades can only go down.
9c. [done, see docs/reports/2026-10-29-model-scoreboard.md] Model-layer scoreboard on the tuning sites (a person asked for it on 10-29 and approved the spend; caps
    below). Question: what do SAM, the Wonder votes and the Spark review add on top of the frozen detector, and do
    they ever lower a real piece? Input: the frozen-v1 lists for the eight tuning strips with landers/shape_v3.json
    applied (the data worktree beside this one holds them under out/shape_v3/; rebuild from the tag if needed).
    Per strip: SAM on the top 20, three Wonder votes on the top 10, one Spark review; real backend, one ledger,
    caps LANDERS_CAP_SAM=200, LANDERS_CAP_WONDER=260, LANDERS_CAP_SPARK=120, about 20 USD at docs/models.md
    prices. Score before and after against controls/tuning.json: recorded pieces in the top 20 whose grade was
    lowered (by which stage, citing its evidence), false alarms per strip lowered, kept and unassessed, and the
    cost per false alarm removed. Publish the ledger and records with scripts/models_publish.py. No change to
    the detector, thresholds or model prompts in this item: a change found here goes in a later tag.
9d. [done, see docs/reports/2026-10-29-fewshot.md; stopped at the probe by its own rule, no votes; dropped on 10-30, no further few-shot work, its budget moved to item 14 cast] Few-shot Wonder, after 9c and judged against it (a person asked for it on 10-29; spend approved up to about
    35 USD; caps LANDERS_CAP_SAM=50, LANDERS_CAP_WONDER=300, LANDERS_CAP_SPARK=120). Each Wonder vote also gets a
    small set of reference crops at the candidate's scale: real pieces from controls/tuning.json and typical false
    alarms from the scored lists, labelled only "hardware example" or "natural example", rotated to the
    candidate's sun direction, with no ids, names or positions anywhere in the prompt. Leave one site out: when a
    strip is voted on, every example comes from the other five sites. Same candidates and same scoring as 9c, so
    the two tables line up; report the change per stage and the cost. Rerun the recognition probe with examples
    attached first: if examples make Wonder name a site or mission, stop and report. The few-shot prompt is a new
    prompt version behind a flag, default off; adopting it for the search is a person's call and goes in a later
    tag (frozen-v2), shown beside frozen-v1.
    Note after 9c (10-29 evening): 9c's Wonder cap ran out on review checks, so three strips got few or no
    votes. Make 9d a votes-only comparison so the arms line up: first fill the missing no-example votes on the
    top 10 of those three strips, then the few-shot votes on the top 10 of all eight; reserve each strip's vote
    calls before anything else can spend them; no Spark reviews in this item. Caps: LANDERS_CAP_WONDER=340,
    LANDERS_CAP_SAM=0, LANDERS_CAP_SPARK=0.
9e. [ ] Frost test at Phoenix, after 9d (a person asked for it on 10-29; no model calls, no new downloads). Question: in
    the frost season, does hardware look different from the frosted ground, and in which direction? Use the two
    frost-season Phoenix strips named in docs/data.md, for this test only: register each to the summer strip that
    holds the key, carry the recorded Phoenix pieces across, and measure each piece against the ground around it
    (brightness contrast, size, a shadow if any) beside the same numbers for the top false alarms of the summer
    list at the same places. Three pieces at one site is evidence, not proof: say so in the report. If the pieces
    stand out where the false alarms do not, propose the check for the top MPL candidates on their spring strips.
    Nothing here changes the detector or frozen-v1.
10. [done, see docs/reports/2026-10-29-heldout-run.md] Held-out run: detector and thresholds frozen (tag), a person triggers it, three sites, once. Then
    Beagle 2, once. A miss at Beagle 2 is a reported result. Triggered by a person on 10-29 through the queue:
    run the detector as it is at frozen-v1 (no code change in this item) with --frozen over the strips of the
    heldout and final_exam groups, write the candidate files and the run log, commit the code state and a
    short report of what ran (strips, tiles, time), and stop. Do not score: the person runs scripts/score.py
    --heldout once on those files.
11. [done for detection and persistence, see docs/reports/2026-10-30-search.md; the model stage on survivors moved to the v2 budget (Decisions 10-30 07:00: votes on search survivors about 35 USD, run on the frozen-v2 list)] The search: 2007 PSP strips first, then the rest of the 34 MPL summer strips; persistence across dates
    for every survivor; a coverage map (what was searched on how many dates) as a result in its own right.
11a. [done, see docs/reports/2026-10-28-search-bookkeeping.md] Search bookkeeping, no detector runs, parallel with items 6 to 8: an inventory of the MPL strips on
   disk (id, date, Ls, incidence, map scale, valid area), which pairs overlap and by how much, the 2007 PSP
   strips first; a coverage map on the polar grid (valid area per strip, number of dates per cell) as a
   figure and a JSON; a tiling plan with tile counts and a time estimate from baseline v1's tiles per
   second (out/baseline_v1/run.log). Outputs under out/search/, a report, and a `scripts/search.py` that
   item 11 will run with the frozen detector. Touches only landers/search/, scripts/search*.py, tests, docs.
12c. [paused: (a), (b) and (d) done, see docs/reports/2026-10-30-disk-work.md and docs/reports/2026-10-30-blind-download.md; (c) the delete stays on hold for the person] Disk work, after the v1 search pass (item 11) finishes, in this order:
    (a) persistence over the strip pairs sharing 10 km2 or more, caching the registration nodes;
        item 11 already ran persistence over all 81 pairs (38 registered): reuse it, cache the registration
        nodes, resample the 0.5 m strip before registering, and retry the failed pairs among those sharing 10 km2 or
        more;
    (b) crop export for every strip: the top 2,000 candidates, all recorded pieces, the sham cuts and the
        transplant target tiles, native resolution, plus every .LBL; and a check that lists, per strip, what was
        exported and confirms each file reads back;
    (c) stop and show the check to the person; after the person approves, delete the .JP2 files only (keep every
        .LBL and the manifest);
    (d) download the two strips of the new blind set (the person names them; one is a re-download of a spare
        strip deleted in the 10-29 cleanup). The person seals the blind key for both before any v2 scoring; no
        agent looks at either strip.
    Limit, written here on purpose: after the delete, items 13 and 14 run from the exported crops. Items 15 and 16
    need full strips, so they can be tested only on the tuning strips that stay on disk; they do not run over the
    search area unless the person asks for a re-download.
12d. [done, see docs/reports/2026-10-30-blind-download-2.md] Download the replaced strip of the blind set (10-30 17:17, person: one blind strip did not contain its target, so controls/sites.json now names a different one; the old file is deleted). Run scripts/fetch_blind.py with a new record, docs/reports/2026-10-30-blind-download-2/fetch.json; it skips files already complete. Same rules as 12c(d): bytes only, nothing opened or parsed, no agent looks at the strip. If its free-disk floor refuses the download, stop and say how many bytes are missing; do not delete anything. Short report, then mark done.
13. [done, see docs/reports/2026-10-30-reranker.md; the rule is not met and nothing is adopted; item 14's list and the two no-texture strips wait for the person in docs/proposals/reranker-v1.md] v2, A: learned re-ranker (first, highest value). Keep the proposer. Crop each candidate, embed it with a
    frozen pretrained open-weight vision model (say whether it counts toward the hackathon's Meta model
    requirement), and train a small classifier, logistic regression first: positives are the recorded pieces
    plus transplanted copies, negatives are the top false alarms of the tuning lists. Evaluate leave one site
    out over all ten tuning sites; exclude the left-out site's pieces from the transplant positives. Add a
    per-strip novelty score (distance from that strip's own candidate population) as one input. Decision rule,
    fixed before any run: adopt only if leave-one-site-out recall@20 beats frozen-v1 on both boards (key and
    transplant) and no recorded piece drops out of the top 20. Proposal to docs/proposals/, adoption by a
    person. The Mac has 8 GB: one embedding pass at a time, small crops, results written as they land.
    Changes after the risk review (10-30 morning): negatives include the sham cuts, so a paste seam alone earns
    nothing. Positives include the native crops of the real pieces, not only transplanted copies; in the
    leave-one-site-out results compare each piece's native score with its transplanted copies, and if the copies
    score clearly higher, report that the model is learning the paste. Logistic regression on a frozen embedding,
    nothing bigger; report the leave-one-site-out spread, not only the mean. Re-rank the top 1,000 to 2,000 per
    strip; pieces the proposer never listed count as misses in the completeness map, not as out of scope. The Mac
    has 8 GB: a small encoder (DINOv2 small or base, or Meta's Perception Encoder at a similar size), small batches,
    nothing else running. Check in the hackathon guide whether that encoder counts toward the Meta model
    requirement and quote the line; do not assume.
14. [done, see docs/reports/2026-10-30-deep-pass.md; published in item 14a] v2, B (10-30 15:45: run on the combined list from item 13, each candidate's better rank of frozen-v1 and the re-ranker, labelled everywhere as chosen after seeing item 13's result and judged only by the blind run, shown beside frozen-v1; if MODEL_API_KEY or LANDERS_REAL_CALLS is missing, do the pricing and the dry run, then mark the item [paused: waiting for the key window] (not as blocked)): deeper model pass. Wonder votes on the top 100 to 200 per strip instead of the top 10, each strip's
    vote calls reserved before any review check can spend them; Spark records all its verdicts in one turn after
    its fetches; crops draw saturated pixels as bright, not black (the 9d finding). Measure on the tuning strips
    how many false alarms are cleared above each recorded piece and how many pieces rise into the top 20. Price
    it from the ledger first; paid calls only after a person approves the spend and caps in that session.
    Changes on 10-30 morning: run it on item 13's re-ranked list (Saturday if 13 runs long). One vote per
    candidate, three only in a borderline band; the current rule needs three votes, so this item first writes the
    single-vote rule and the borderline band into docs/proposals/ as a new pre-declared rule, before any call.
    Before any call it also adds the cumulative dollar cap (see Decisions, 10-30 07:00), reports the ledger total
    so far, and stops after the first 100 calls to report again. Price target about 32 USD on the tuning strips.
14a. [done, see docs/reports/2026-10-31-vote-orderings.md; recommends no vote ordering and no lowering in 16a's switch, for the oracle and the person; corrects two figures: 34 lowered detections of 128 voted, 12 of them on 9 of the 128 planted pieces, and Spark's four rows are three pieces] Item 14's paid run is complete (10-31 07:00; no more calls in this item). Publish it: experiments/deep14_summary.py, scripts/models_publish.py out/deep14 docs/reports/2026-10-30-deep-pass/run, point the register's item 14 row at the published ledger, and update docs/reports/2026-10-30-deep-pass.md with the real result. Then, with no model call, from the recorded votes, test two orderings the person asked for on 10-31 (labelled post hoc, judged only by the blind run): (a) a candidate whose first vote is hardware moves up the list (say how, and fix it before looking at the boards: e.g. ahead of every unvoted or natural candidate at its strip's same depth band); (b) votes change only the order, never the grade: natural confidence pushes a candidate down, hardware pulls it up, nothing is lowered to likely natural. Report the recall-at-N curve on key and transplant for frozen-v1, combined, combined + vote rule, (a), (b), with 95 percent intervals, and list every recorded or planted piece that moves out of the top 20. Note separately: the Spark reviews lowered four recorded pieces in the top 20 and the vote rule lowered 34 of 128 planted pieces; say for each planted piece lowered what the crop shows (size, branch) without opening a heldout strip. Write which ordering, if any, 16a's switch should use; the oracle and the person decide. Mark done.
15. [done, see docs/reports/2026-10-30-halfcal.md; the rule is not met and nothing is adopted; one question for the person in docs/proposals/halfcal-v1.md] v2, C: per-strip calibration with an honest tail: fit the top of each branch on one half of each strip and
    check it on the other half, instead of extrapolating. Same judging as A.
15a. [done, see docs/reports/2026-10-30-halfcal-column.md; order unchanged on every list; item 17 must run the column on the frozen list] v2, C follow-up (person, 10-30 18:43): add item 15's half-fitted rate as a column beside each candidate's score in the v2 list, the case board and the published candidate files, with the order unchanged and frozen-v1's columns untouched; a test that the order is identical with and without the column. Small diff; report, then done.
16. [done, see docs/reports/2026-10-30-darkrelief.md; the rule is not met and nothing is adopted; no question for the person] v2, D, if time allows (cut first if the schedule slips): a two-sided shadow test for dark candidates (dark
    on the anti-sun side, not on the sun side), aimed at dust-covered hardware. Same judging as A.
    For every v2 item: report the full recall-at-N curve (10, 20, 50, 100, 250) for every board, frozen-v1 beside
    v2; any number on the four sites that were sealed for frozen-v1 is labelled "not blind".
16a. [done, see docs/reports/2026-10-31-v2-assembled.md; exact on the strips with true frozen-v1 lists; item 13's lists for six older strips differ slightly from the tagged detector; persistence on v2 and the search's vote depth are left for item 17] v2 assembled for the freeze (person asked to start 10-31 06:23; item 14's paid run finishes in parallel). Build one command that runs v2 end to end on a strip: frozen-v1 detection and thresholds unchanged; the ranking is item 13's combined list (each candidate's better rank of frozen-v1 and the re-ranker, labelled everywhere as chosen after seeing item 13 and judged only by the blind run); item 15a's rate column; then the model stage from item 14 behind one switch, off by default, which the oracle sets from item 14's published result (a vote can only lower a grade). Make it run on a strip it has never seen without reading any key or index file, and from the full strip, not the exported crops. Prove it on two tuning strips: it reproduces item 13's combined-list ranks and item 15a's column exactly, with the model stage off and on the fake backend. Write docs/reports/<date>-v2-assembled.md listing every file and number that the tag would freeze, and the exact commands for the blind run and the search. Do not tag, do not run on any heldout strip, no paid call. Mark done.
16b. [done, see docs/reports/2026-10-31-v2-search-prep.md; 34 of 34 strips, preparation only, marked unfrozen and run through 16a's library because scripts/v2.py refuses before the tag; item 17 reruns from the tag and compares byte for byte] v2 search prep, after 16a (person, 10-31 06:28: no idle time). With 16a's command and nothing else changed, compute the re-ranker score, the combined rank and the rate column for every candidate already listed on the 34 search strips by item 11 (frozen-v1 detection is unchanged, so its candidates stand). Per strip, written as it lands, resumable. Model stage off, no paid call, no heldout strip. If 16a's command changes after the freeze, this is rerun from the tag; until then it is preparation only and nothing is published from it. Short report with timings per strip, then done.
17. [done: tagged frozen-v2 at c99c14e by the person, 10-31 10:45] v2 freeze. The rest of the old item 17 is split into 17a to 17d below.
17a. [running] Blind run (person asked 10-31 10:31 that the rest run by itself). Run the frozen command from docs/reports/2026-10-31-v2-assembled.md on the heldout group's strips exactly as written there, from the tag, model stage off, --jobs 2 (another agent shares the Mac). Do not open, view, crop or describe those strips or their lists beyond what the command writes; do not run score.py --heldout (the person scores). Write the run record (commit, timings, files written) and stop. Done.
17b. [ ] v2 search over the 34 MPL strips, from the tag: the commands in docs/reports/2026-10-31-v2-assembled/search_commands.txt, 2007 PSP strips first, resumable, each strip's output committed as it lands, --jobs 2. Then the whole-list command. Report with timings, list sizes per strip and the area covered. Done.
17c. [ ] Persistence and completeness on v2: the small option 16a describes (survivors from candidates_v2.json, look-ups against the whole lists, cached registration nodes), run over the pairs; then the completeness map: per area, the chance that MPL-like hardware there would rank in the top N, from transplant recall per strip (use the transplant board's numbers per terrain, and say plainly where an area was seen on one date only, which caps it at needs second look). Report. Done.
17d. [ ] Case board on the real results: the v2 search's top candidates per strip that persist, both dates, the fixed verdict words, the completeness map, and the blind-run board once the person has scored it (leave a placeholder until then). Static HTML. No model call. Report. Done.

12. [ ] Write-up and video: one solved case re-found blind, then the open case with coverage and the graded
    list; every number from a results file.
12a. [done, see docs/reports/2026-10-28-case-board.md] The case board, parallel with items 6 to 8: a static HTML page built from results files only
   (candidates with grades, test outcomes, persistence, SAM measurements, votes, verdicts, the ledger and
   the coverage map), fixed vocabulary, every number traced to the file it came from, built and tested on
   the fake backend's outputs; no model call. Touches only landers/board/, scripts/board.py, tests, docs.

## Timing rules

- Baseline before key. The key stays in a private copy until the baseline run is committed.
- controls/heldout.json never enters the repo or an agent's context. Held-out strips are never tuned on.
- thresholds, calibration tables, control files and any published number: proposed by the agent, adopted by
  a person, versioned.
- A frozen tag before the held-out run and before the search. Nothing changes after a frozen run starts; a fix
  goes in a later tag and both numbers are shown.
- The two frost-season Phoenix strips (named in docs/data.md) are not used, except in item 9e. Pathfinder is 50 cm/px.

## Backlog (ideas with a when)

- More dates per control site from the PDS Orbital Data Explorer: every extra date is a known answer and a
  persistence pair. Any time, disk permitting. Fetch code lives in the repo and logs the credit line.
- Spark bounded follow-ups (order a zoom pass, a second-date check, three more votes), each capped: with
  item 9 if time allows; the agent story for the video.
- Open-weights Muse Spark Open through a hosted provider as a second review backend: only if ahead.
- Moon: LROC NAC images of Apollo descent stages, Surveyors, Lunokhods and crash sites as a generalisation
  test (different camera, format and light). After the submission.
- Early-spring MPL strips (mpl_other) as a thermal test: hardware defrosts before the ground. After the
  search, if time.
- Sheet branch and saturation: the one recorded saturated canopy sits 0.01 above the flatness threshold on its
  tile, and a fully saturated sheet is invisible to the branch. Measure both with transplant injection (item 7)
  before touching the flatness test.
- SAM terrain vocabulary for polar ground ("polygon", "frost", "rock", "ripple") chosen on one real MPL tile
  and recorded with the tile id. With item 9.

## Decisions (dated)

- 2026-10-28: name Finding Landers; six tuning sites, three held out, two spare, Beagle 2 final exam;
  thresholds v0 (5 m match radius, top 20, recall 0.8, 2 false alarms per km2); scores calibrated to a
  false-alarm rarity scale fitted on phase 0 tiles and measured on phase 1; Wonder advisory, never gating;
  "candidate" requires two dates; the parachute may already be dust-covered after seven years, so the hard
  metal is the long-lived signature; wind moves fabric and foil, never metal.
- 2026-10-28 (evening): thresholds v1 adopted from docs/proposals/scoring-v1.md: one candidate matches at
  most one piece; pieces scored as hardware, fabric or mark; marks matched at 20 m. The first score reads
  2 of 13 under v1 (3 of 13 under v0); both are kept (docs/reports/2026-10-28-first-score-rescored.md).
  The key holds 13 of 22 pieces; the Schiaparelli and Phoenix positions were checked against the HiRISE
  captioned images by registration, which corrected one piece.
- 2026-10-29 (02:00): landers/shape_v1.json adopted (the saturation rule from docs/proposals/shape-rules-v1.md;
  6 of 18 against 3 of 18 on the key). The tuning bar for item 8 is the one written in item 8. The 46
  search-strip tiles listed in out/transplant_t1 are the injection tuning ground: a fixed, listed set,
  0.3 percent of the search area, chosen by sun angle; the search still runs the frozen detector over every
  tile including these, and the small chance that a real piece sits in one of them and is tuned against is
  accepted and written here. Nothing else from the search area is used for tuning.
- 2026-10-29 (02:40): landers/shape_v2.json adopted, all three new rules (docs/proposals/shape-rules-v2.md): key
  8 of 18, hardware 7 of 12, injection hardware 35 of 72, fabric 9 of 24. tile_top is conditional on the
  leave-one-site-out check written into item 8.
- 2026-10-29 (08:20): landers/shape_v3.json adopted (tile_top withdrawn after the leave-one-site-out check). One
  more tuning session, detector changes only (calibration per terrain, the fabric branch), then the frozen tag
  tonight; the search runs on the frozen detector from Thursday night.
- 2026-10-29 (16:10): tag frozen-v1 at 4f4253e (detector v0.4 in table mode, landers/shape_v3.json, thresholds
  v1), pushed. Item 8's third session kept nothing (docs/reports/2026-10-29-tuning-loop-3.md). Item 11 starts now
  on the frozen detector; item 10 runs after it, once the held-out key is sealed. In item 11 the model calls on
  survivors cost money: stop before them and mark the item blocked for a person.
- 2026-10-29 (17:20): held-out key sealed after the tag and before any held-out run: controls/heldout.json (not in
  git) holds 11 positions over the three held-out sites and the Beagle 2 lander on its three strips; sha256
  9b54704be5ba929ce996d7b0a77c89ac61565057d9c4e27cfa8448d4283da372. Three pieces have no position and are excluded
  from recall (two fall in a CCD gap of their strip, one had moved away); the reasons are in the sealed file.
  Held-out strip crops used to seal it were never seen by an agent.
- 2026-10-29 (21:20): held-out scored once by a person (score files kept outside the repo until the write-up, because the leak check bars sealed site names). Recall at
  20: 0 of 11 at the three held-out sites, 0 of 3 for Beagle 2. Below the pass line; reported as it is. Best
  ranks: 25, 44 and 81 out of about 30,000 candidates on one strip; most others between 300 and 2,100; two pieces
  not detected. Nothing is retuned against this result; any fix goes in a later tag, shown beside frozen-v1.
- 2026-10-30 (02:30), the person's decisions after the frozen-v1 held-out result:
  1. History stays: no commit, report or score is rewritten, squashed or deleted.
  2. The three sites sealed for frozen-v1 and the final-exam site become tuning sites for v2. Their held-out
     scores stay above as the frozen-v1 result; any v2 number on them is reported as "not blind". The person
     moves their positions into controls/tuning.json; no agent opens the sealed file.
  3. A new blind set for v2: the spare site with a lander still on the surface, and one new strip of the other
     spare site taken with a lower sun than the strip on disk (chosen by the person from label metadata only).
     The person seals the key for both with a hash before any v2 work is scored. Neither is tuned on or looked
     at by an agent.
  4. The README lists only the models the pipeline calls and what each does.
  Goal: the best detector for MPL plus an honest measure of how much to trust it. Work items 13 to 17, judged on
  the key and the transplant board against frozen-v1 with each decision rule written before its run; proposals to
  docs/proposals/, adoption by the person. Item 11 (the search on frozen-v1) finishes and stays as the v1
  record. Schedule: Fri 13 and 14 on tuning strips; Sat 15 (and 16 if ahead), freeze v2 Saturday night; Sun blind
  run and start the v2 search; Mon persistence, completeness map, case board; Tue video; Wed buffer, submit by
  18:00 PT. If something slips, cut 16, then 15, never the video.
- 2026-10-30 (07:00), the person's addendum:
  1. Budget, a hard rule: total Meta Model API spend for the whole project stays under the 150 USD credit. A
     cumulative dollar cap across every run's ledger, not per item: refuse any paid call once the running total
     would pass 120 USD (the gap covers a possible Wonder token undercount in the ledger). Before any new paid run,
     report the ledger total so far for the person to check against the Billing page; after the first 100 calls of
     the next paid run, stop and report again. Item 9d is dropped and its budget moves to item 14. Target
     allocation: item 14 on the tuning strips about 32 USD, votes on search survivors about 35 USD, the blind run
     about 5 USD, Spark and SAM about 10 USD. Each item is priced from the ledger before it runs; paid calls only
     after the person approves in that session. The cheaper contributor model variants are not decided and are
     not used unless the person says so.
  2. Disk order: item 12c, after the v1 search pass, with the limit written there (items 15 and 16 on tuning strips
     only once the search strips are deleted).
  3. and 4. Changes to items 13 and 14, written into the items.
  5. Optional, only if the person confirms Modal credits: test Muse Glimmer as a voter, hosted on Modal, on the
     same tuning candidates Wonder already voted on, compared vote by vote; first confirm Modal serves Glimmer. It
     cannot run on this Mac (about 20 GB quantized) and spends Modal credits, not the Meta credit.
  6. Reporting: every blind score carries its 95 percent interval (3 of 6 is about 12 to 88 percent). The first
     site of the new blind set is the main MPL stand-in in the write-up.
  Cut order if time runs short: item 16, then 15, never the video.
- 2026-10-30 (10:29), the person: (1) the .JP2 delete in item 12c(c) is approved in advance, on one condition the
  agent checks itself: the read-back check passes for every strip (every listed crop and every .LBL reads back and
  the counts match what was asked for). If any strip fails, delete nothing for that strip and stop. Keep every .LBL
  and the manifest. (2) The blind key for the two new sites is placed by the oracle from published captioned
  images, as for frozen-v1, and sealed by the person with a hash; no agent sees either strip. (3) Item 13 may start
  from the exported crops as soon as 12c's export check passes, without waiting for the downloads. (4) Item 14's
  paid run is approved within the 10-30 07:00 budget rule: price it first, report the ledger total, run with the
  cumulative cap at 120 USD, stop after the first 100 calls and report for the person to compare with the Billing
  page before going on. The paid calls need MODEL_API_KEY and LANDERS_REAL_CALLS=1 in the environment of the
  window that runs item 14; without them the item stops at the price and the dry run.
- 2026-10-30 (15:45), the oracle deciding for the person, at the person's request, so the Mac does not sit idle:
  item 14 runs on the combined list (post hoc label, judged only by the blind run, frozen-v1 shown beside it);
  item 14's pricing and dry run run now, its paid calls wait for the key window; item 12c(d) downloads the two
  blind strips now (they fit in the free disk without the delete; no agent opens them, the oracle places the key
  from published captioned images, the person seals it); item 15 runs on the tuning strips after that. The JP2
  delete and the two no-texture strips stay for the person. Order: 12c(d), 14 (dry), 15.

- 10-30 17:17 (person, then oracle in the person's absence): one strip of the blind set did not contain its target (its footprint missed the site by several km); the person approved a replacement, chosen by the oracle from the HiRISE index (footprint polygon contains the site, the CCD holding the target present, late-summer season, sun angle close to the other blind strip), and the delete of the old file. controls/sites.json updated; item 12d downloads it. Item 15's result stands as reported; nothing adopted.
- 10-31 01:10Z (oracle, person away): the v2 blind key is written to controls/heldout.json (gitignored; copy outside the repo), sha256 5f6f189ef631ce45ddecb406d7f3e270edfe66412c2281682dcbd8fa329c368f, from published captioned images, before any v2 run; the person seals it. Item 16 queued next.
- 10-30 18:43 (person): one more lander joins the scored pieces of the blind set (controls/sites.json; the oracle rewrote the key, sha256 f249f93b3a4cf893f25f3c1c15286f6d95ca6fcbb3f408afd4deff63959aeb87, replacing the 01:10Z hash); the two caption-marked likely pieces at the other blind site stay unscored. Item 15's half-fitted rate is shown as a column beside each v2 candidate's score, with no change to the order (item 15a). The JP2 delete of 12c(c) is not done: it waits until the disk is short again, because 11 of 32 tuning pieces are outside the exported top 2,000.
- 10-30 21:58 (person): the v2 blind key is sealed; the person checked sha256 f249f93b3a4cf893f25f3c1c15286f6d95ca6fcbb3f408afd4deff63959aeb87 without opening the file. Billing page read before item 14's paid run: about 6 USD, against 8.3289 on the ledgers (the ledger runs high; Billing may also lag).
- 10-31 06:20 (person): no more pauses for a billing check during paid runs; the cumulative 120 USD cap and each run's own --max-usd limit stay. Item 14's run went past its 100-call pause on 10-30 (passing --billing-usd skips the pause); 36.025 USD this run, 44.3539 USD on all ledgers; remaining transplant votes and reviews about 7.5 USD.
- 10-31 06:30 (person): paid runs are limited only by the total budget (under 150 USD; the code's cumulative 120 USD stop stays as the safety margin). No per-run pauses and no small per-run limits: a run's --max-usd is set to what is left under the total. The tag and the blind scoring stay the person's; the oracle tells the person ahead of time when each is coming.
- 10-31 07:00 (oracle): item 14 finished; 40.3514 USD this run, about 48.68 USD on all ledgers. Read from the summary (not yet published): key at N = 20 is frozen-v1 8, combined 16, combined + vote rule 18, + Spark review 15; transplant 15, 21, 20. The vote rule lowered no recorded piece but lowered 34 of 128 planted pieces; the Spark review lowered four recorded pieces in the top 20. So the Spark review stays out of v2, and the vote rule does not lower grades in v2 until item 14a says otherwise. Item 14a next, then 16b.
- 10-31 10:31 (person): Finding Landers runs itself to the end and is then wrapped. The model stage stays off in frozen-v2 (14a: neither vote ordering holds up on the transplant board; the vote rule's +2 key and -1 transplant sit inside the intervals). After the search, Wonder votes on the top candidates as a recorded opinion on the case board only, never changing rank or grade. No deeper-list test.
