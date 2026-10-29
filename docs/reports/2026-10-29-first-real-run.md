# Report: the first real model run (2026-10-29)

Plan item 9b, branch `claude/model-layer`. The person had exported `MODEL_API_KEY` and `LANDERS_REAL_CALLS=1`
and the loop prompt named this item, which I took as the ask the item requires. Every number below is
copied from `docs/reports/2026-10-29-first-real-run/summary.txt`, which `experiments/first_run_summary.py`
prints from the published records in that directory; the ledger, every per-stage record, the review's tool
log and the 68 recordings are committed there (`PUBLISHED.json` lists them). The id-to-position manifests
and the input lists stay under `out/models/` and never entered a prompt.

Caps for this run were set to 80 SAM images, 100 Wonder calls and 40 Spark turns through `LANDERS_CAP_*`
(the defaults are 3,000, 300 and 200). Nothing was refused; the total estimate was $1.19.

## What ran, in order

Inputs: the top 200 candidates by score of two strips from the adopted detector run
(`out/shape_v1/candidates_v02b_features_shape_v1sat.json` in the baseline worktree, the saturation rule of
`landers/shape_v1.json`), cut by `experiments/first_run_inputs.py`; and the recorded pieces of the same
strips from `controls/tuning.json`, as a second input list for the probe only.

1. **Recognition probe, the Curiosity strip (ESP_030313_1755)**, top 3 candidates, 3 augmented crops
   each, 9 calls: 4 of 9 answers said recognised. Two of the four named a lander on a comet (confidence
   0.65 each), one a polar scarp on Mars (0.6), and one, on the crop of the recorded parachute
   (candidate c002, 6.8 px from the key position), said "Jezero Crater, Mars, near the Mars 2020 ... landing
   site" and described a backshell and collapsed parachute imaged by HiRISE (0.5). The mission name is a
   sealed site's and is redacted in the committed file.
2. **Recognition probe, the Phoenix strip (ESP_017716_2485)**, top 3, 9 calls: 0 of 9 recognised; every
   answer described polygonal, pitted ground and a small bright or dark speck.
3. **Probe at the recorded pieces** (the strongest memorisation test; the key is readable in reports, not
   in prompts), one plain crop each: Curiosity 1 of 4 recognised, the parachute again as the same other
   mission's parachute and backshell at Jezero (0.45); backshell, heat shield and descent stage not
   recognised. Phoenix 0 of 3 (lander, backshell, heat shield).
4. **SAM 3.1 on the Curiosity top 20**, one box prompt per candidate on a 256 px crop, 20 calls: 20 masks,
   confidence 0.52 to 0.844 (median 0.688); 9 of 20 masks touched the box edge and came back `unsure` on
   every test. Outcomes: `sam_size` 11 pass, 9 unsure; `sam_edge` 10 pass, 1 fail, 9 unsure; `sam_shape`
   1 pass, 2 unsure, 17 not run (sheet candidates make no shape claim). The parachute, c002, measured
   24.31 m equivalent diameter at 256 px (unsure, touching) and 23.27 m on the reviewer's 512 px zoom
   pass (pass, edge contrast 2.0).
5. **Muse Wonder votes on the Curiosity top 3**, 3 augmentations each with a reference crop from the
   Spirit strip (ESP_025815_1655), 9 calls: c000 and c001 (sheet false alarms) got natural 0.62, 0.7,
   0.65 and natural 0.62, 0.7, 0.65; c002, the parachute, got hardware 0.72, 0.78, 0.75, each reason naming
   straight edges, a fold and a shadow. The vote rule (two natural at 0.7 or more, none hardware) lowered
   nothing: only one natural vote per false alarm reached 0.7. The ledger's totals are 34 Wonder calls
   (9 + 9 + 4 + 3 + 9) and 22 SAM images (20 plus the reviewer's two zoom passes).
6. **Muse Spark review of the Curiosity top 20**, 12 turns (the cap): listed the strip, read the
   thresholds, fetched all 20 records in two parallel batches, then one verdict or check per turn: 5
   verdicts recorded (c000 and c001 lowered from needs second look to likely natural, citing votes and
   the mask; c002, c003, c004 kept), 3 checks ordered (a second-date check, refused as no second date in
   this run; two zoom passes). It hit the turn cap with 15 candidates unreviewed and no final JSON. Every
   verdict passed the citation and copied-number checks on the first try.

Grades moved only down: two false alarms to likely natural by the review; the parachute stays needs
second look, as one date can give. No model raised anything, by construction.

## What I decided and why

- **The run was asked for.** Item 9b says "after MODEL_API_KEY is in the environment and a person asks";
  both gates the real backend checks were exported by the person and the loop was started on this item by
  number, skipping item 8. The caps were tightened for the first run anyway.
- **Curiosity for the full pass.** The adopted run has two recorded pieces of that strip in the top 20
  (parachute rank 3, backshell rank 9 per `out/shape_v1/score_v02b_features_shape_v1sat.json`), so the
  models had real hardware to measure and vote on. The probe ran on it and on Phoenix first, as the item
  says, so the votes are read knowing what the probe said.
- **The probe's reading.** Wonder did not identify either place or either mission. On the one crop that
  holds a parachute and backshell it named the wrong, more famous mission, which says it recognises the
  class of object from orbit, not the site. The comet answers on two bright patches are fabrications at
  0.65. So the votes are advisory as designed, and the one thing to read into them is that "hardware"
  from Wonder means "looks like descent hardware", with no evidence it means "I know this image".
- **Two fixes before the first paid call**, both found without the network: `meta-sam-parser` is async
  and its records are not what item 9 assumed (half-open boxes, string ids, masks covering only their
  bounds), so the real SAM backend now goes through `parse_sam_events` and `sam_result_from_records`,
  unit tested on constructed records (`tests/test_models_sam_parse.py`); and the dry run on a real strip
  stopped on the thresholds file's `decided_on` date reaching the reviewer, so `read_thresholds` drops
  the provenance fields. The dry run of all five commands on the real strips (`--backend dry-run`) came
  first and the wire requests were read before anything was sent.
- **Publishing with redaction.** A model's free text named a sealed site. `scripts/models_publish.py`
  copies a run out of `out/` with sealed-site names replaced by a marker and counted (10 replacements in
  4 files here, all the same name in answers about the parachute crop and in their recordings); numbers
  are never changed, manifests are never copied. `scripts/leakcheck.sh` is clean on the result.
- **Not rerun.** The review's turn cap is a design shortfall (one verdict per turn after fetching
  twenty), not a failure of the run; the item asked for one review, and that is what is recorded.
- `docs/proposals/sam-tests-v0.md` is rewritten from the twenty masks, as the item 9 report asked. The
  limits stand; the change it asks for first is the sheet branch's box padding, not a threshold.

## What to check by eye

The reviewer lowered c000 and c001 on the strength of three Wonder votes each and the mask. Their
positions are in `out/models/manifest_ESP_030313_1755.json`; the votes call them diffuse bright patches
with no outline or shadow, and the masks had 21 and 5 pieces. If a person disagrees with either, the
vote rule and the reviewer's use of votes are the things to tune, not the detector.

## What I would do next

- Review loop: ask for all verdicts in one turn (the model already batched its fetches), or raise
  `MAX_TURNS` for a 20-candidate strip; with the cap at 12 the review covers 5 of 20.
- Sheet-branch box padding 1.5 in `sam_pass` (the zoom pass's setting), then re-measure the proposal.
- Wonder's token accounting: 497 prompt tokens for three images is far under docs/models.md's estimate;
  the ledger's Wonder cost is therefore an underestimate until a person checks the bill against it.
- The vote rule's 0.7 bar: the two false alarms had votes at 0.62, 0.7, 0.65; a rule on the mean (0.66
  against the parachute's 0.75) would have lowered them without the reviewer. A proposal, measured on
  more strips, not a change.
- Replaying this run costs nothing: `--backend recorded --out-dir docs/reports/2026-10-29-first-real-run`
  answers every request from the committed recordings.
