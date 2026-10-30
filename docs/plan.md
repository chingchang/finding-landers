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
9d. [running] Few-shot Wonder, after 9c and judged against it (a person asked for it on 10-29; spend approved up to about
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
11. [ ] The search: 2007 PSP strips first, then the rest of the 34 MPL summer strips; persistence across dates
    for every survivor; a coverage map (what was searched on how many dates) as a result in its own right.
11a. [done, see docs/reports/2026-10-28-search-bookkeeping.md] Search bookkeeping, no detector runs, parallel with items 6 to 8: an inventory of the MPL strips on
   disk (id, date, Ls, incidence, map scale, valid area), which pairs overlap and by how much, the 2007 PSP
   strips first; a coverage map on the polar grid (valid area per strip, number of dates per cell) as a
   figure and a JSON; a tiling plan with tile counts and a time estimate from baseline v1's tiles per
   second (out/baseline_v1/run.log). Outputs under out/search/, a report, and a `scripts/search.py` that
   item 11 will run with the frozen detector. Touches only landers/search/, scripts/search*.py, tests, docs.
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
