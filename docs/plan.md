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
3. [ ] Key filled by a person from the sheets and grids, in a private copy. Copied to controls/tuning.json and
   committed only after item 1 is committed.
4. [ ] First score: baseline v1 against the key. This is the blind number; report it as such.
5. [ ] Persistence: local registration (phase correlation on a 512 px window) between the two Schiaparelli
   dates and the two Phoenix dates; measured offsets in a report; a persistence branch that matches position
   only. Hard parts (lander, backshell, heat shield, fragments) must sit in the same place on both dates to
   reach "candidate". Sheets get a 50 m radius and are never marked "likely natural" for moving or vanishing.
   Absent on a later date is weak evidence (burial) and returns unsure, never fail.
6. [ ] Shape features into the score, only where real pieces sit in the top few percent of that feature's
   false alarms on the same strip; each threshold recorded and versioned. Two-sided shadow test (dark on the
   anti-sun side and not dark on the sun side), shadow length consistent with a 1 to 3 m height, isolation.
7. [ ] Transplant injection: cut each confirmed piece at full resolution from its tuning strip and plant it
   into MPL-strip tiles with matched incidence; score as injection. Nothing cut from, or planted into, a
   held-out site. This becomes the main scoreboard for tuning; the six real sites stay a constraint.
8. [ ] Tuning loop, unattended: one change, score, keep or revert, one line in docs/experiments.md; tuning
   tiles only; proposals for thresholds in docs/proposals/, adopted by a person.
9. [ ] Model layer, after MODEL_API_KEY is in the environment and a person asks: SAM 3.1 box prompts at zoom
   for size and shape of every survivor; Muse Wonder advisory votes (recorded, never gating) with the
   recognition probe run first on Curiosity and Phoenix; Muse Spark review that can keep or lower a grade,
   never raise it, with every call through a ledger with a hard cap. First real run: one tuning site, 20 SAM
   calls, 9 Wonder votes, one Spark review.
10. [ ] Held-out run: detector and thresholds frozen (tag), a person triggers it, three sites, once. Then
    Beagle 2, once. A miss at Beagle 2 is a reported result.
11. [ ] The search: 2007 PSP strips first, then the rest of the 34 MPL summer strips; persistence across dates
    for every survivor; a coverage map (what was searched on how many dates) as a result in its own right.
12. [ ] Write-up and video: one solved case re-found blind, then the open case with coverage and the graded
    list; every number from a results file.

## Timing rules

- Baseline before key. The key stays in a private copy until the baseline run is committed.
- controls/heldout.json never enters the repo or an agent's context. Held-out strips are never tuned on.
- thresholds, calibration tables, control files and any published number: proposed by the agent, adopted by
  a person, versioned.
- A frozen tag before the held-out run and before the search. Nothing changes after a frozen run starts; a fix
  goes in a later tag and both numbers are shown.
- The two frost-season Phoenix strips (named in docs/data.md) are not used. Pathfinder is 50 cm/px.

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
- SAM terrain vocabulary for polar ground ("polygon", "frost", "rock", "ripple") chosen on one real MPL tile
  and recorded with the tile id. With item 9.

## Decisions (dated)

- 2026-10-28: name Finding Landers; six tuning sites, three held out, two spare, Beagle 2 final exam;
  thresholds v0 (5 m match radius, top 20, recall 0.8, 2 false alarms per km2); scores calibrated to a
  false-alarm rarity scale fitted on phase 0 tiles and measured on phase 1; Wonder advisory, never gating;
  "candidate" requires two dates; the parachute may already be dust-covered after seven years, so the hard
  metal is the long-lived signature; wind moves fabric and foil, never metal.
