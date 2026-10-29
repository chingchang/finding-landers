# Report: the model layer, built blind (2026-10-28)

Plan item 9, branch `claude/model-layer`. No key, no network, no strips on disk in this worktree: everything
below runs on the fake backend and synthetic arrays, and nothing here is a result about Mars.

## What was built

`landers/models/` and three scripts, as docs/models.md asked, with one interface for the three models:

- **The leak guard** (`leak.py`). Every text and every image of every request is checked before the ledger
  is charged: observation ids, file names, dates, coordinates with a bearing, the names and the published
  coordinates (three or more decimals) of every site in `controls/sites.json`, a list of mission and
  region words, and PNG text chunks. The error says the kind and the offset, never the matched text, so a
  sealed name cannot reach a log through the guard itself. The fixed prompts, tool definitions and schemas
  pass the guard and a test keeps it so.
- **The ledger** (`ledger.py`). Per model: units (SAM images, Wonder calls, Spark turns), attempts, ok,
  failed, refused, tokens and a cost estimate at the prices in docs/models.md; hard caps 3,000 / 300 / 200
  with `LANDERS_CAP_<MODEL>` overrides; charged before the call, every retry counted; continues from
  `out/models/ledger.json` across runs.
- **Backends** (`backend.py`). `fake` (SAM: a disc inside each box at confidence 0.9; Wonder: a schema-valid
  record that says unsure; Spark: a scripted review that lists, fetches, reads thresholds, keeps every
  candidate and answers), `recorded` (replay by request hash; records when wrapped around another backend),
  `dry-run` (writes the wire request with images replaced by hash and size, answers from the fake), `real`
  (the `openai` SDK, imported lazily, built only with `MODEL_API_KEY` and `LANDERS_REAL_CALLS=1` in the
  environment, always wrapped in `recorded`). The `ModelClient` retries a 429 or 5xx at most three times
  with backoff and never retries a 400.
- **SAM** (`sam.py`). The box-prompt string from the documented grammar, a box from the detector's blob
  padded by its own size, mask measurements (area, equivalent diameter, major and minor axes, elongation,
  fill, circularity, edge contrast, whether the mask touches the box) and the size, shape and edge tests
  with outcomes pass, fail, unsure (weak confidence or a mask on the box edge) or not run. The size limits
  are the detector's own branch ranges; the two new limits are in `docs/proposals/sam-tests-v0.md`.
- **Blind crops** (`crops.py`). Built from arrays only; a 256 px square at native resolution, its centre at
  4x by pixel repetition, an optional reference crop stretched and flipped the same way; three identical
  channels, no metadata; seeded augmentations (offset, flips, four stretches), the first vote always plain.
- **Wonder** (`wonder.py`). The vote schema (verdict hardware, natural or unsure; confidence; one-sentence
  reason) and the probe schema (recognised, place, shows, confidence), fixed question text first for the
  prefix cache. `apply_votes` lowers one step on two natural votes at confidence 0.7 or more with no
  hardware vote at that confidence; never raises; leaves "not assessed" alone.
- **Spark** (`spark.py`). The five tools over an evidence store built from a whitelist (branch, grade,
  score, area, shape features, test outcomes, persistence seen flag, SAM measurements, votes; no row,
  column, id, coordinate or date). `record_verdict` rejects raise, empty citations, unknown fields, any
  number not copied from the record, and discovered, confirmed, proven. `request_check` runs a bounded
  zoom pass, more votes or a second-date check through the same ledger and returns a cap as a refusal.
  The loop replays the assistant message before the tool results, stops on a reply with no tool calls or at
  the turn cap, parses the strict final JSON and marks any final verdict that was never recorded.
- **Scripts.** `scripts/models_sam.py`, `scripts/models_wonder.py` (`--probe`), `scripts/models_review.py`;
  outputs under `out/models/` with an id-to-position manifest that stays there.

Tests: `tests/test_models_guard.py` and `tests/test_models_pipeline.py`; `uv run pytest -q` and
`scripts/leakcheck.sh` are green at this commit. The test count is whatever that command prints.

## What I decided and why

- No new dependencies. Adding `openai` would have needed the network this item forbids, so the real
  backend imports lazily and names the install step; 9b starts with `uv add openai meta-sam-parser`.
- The published-coordinate rule in the runtime guard needs three decimals. The first end-to-end test
  aborted because an ordinary measurement equalled a two-decimal site coordinate; a value at 1 km
  precision locates nothing by itself, and a run that dies on it protects nothing. The committed-file check
  keeps the strict rule, and it caught two more things in this very item: a hardcoded word list that
  guessed names of sealed sites (removed; the runtime list now comes from `controls/sites.json` only) and
  a test coordinate that matched a sealed value (replaced by a string).
- The real backend is always recorded, so the first real run can be replayed and re-parsed for free when
  the parser's record attributes turn out to differ from this document's description.
- SAM tests reuse the detector's size ranges rather than inventing new numbers; the two limits that are new
  are a proposal, not a threshold.

## What to check in 9b, before anything else

1. One dry-run SAM request against the real API: the box-prompt separator, the `<0f>` prefix and the
   `strict` key in `response_format`. A 400 on any of these is a one-line fix.
2. The `meta_sam_parser` record attributes used in `RealBackend.sam`.
3. The recognition probe on Curiosity and Phoenix before any vote, as the plan says; a yes goes on the board.
4. Rewrite `docs/proposals/sam-tests-v0.md` from the first twenty real masks before a person adopts anything.

## What I would do next

Item 9b when a person has exported the key and asked; until then items 6 to 8 on the main branch are
independent of this one. A `Monitor`-free way to run the three scripts in sequence on one strip would be
a small `scripts/models_run.py`; I left it out because each stage should be looked at before the next
spends money.
