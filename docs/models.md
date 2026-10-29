# Models: the Meta Model API as this project uses it

What the code needs to know to call SAM 3.1, Muse Wonder and Muse Spark, and the rules around the calls.
Facts here come from dev.meta.ai/docs and the meta-model-cookbook (Oct 2026); where a thing is undocumented
it says so. Read this before building the model layer (plan items 9 and 9b).

## Access

- Base URL `https://api.meta.ai/v1`, OpenAI-compatible: Chat Completions, Responses, Files. The `openai`
  Python SDK works as is: `OpenAI(base_url=..., api_key=os.environ["MODEL_API_KEY"])`. The SDK does not read
  `MODEL_API_KEY` by itself; pass it. The key never appears in code, prompts, logs, results or commits.
- A real call happens only when a person asked for it in this session. The layer is built and tested
  against a fake backend (below); the real backend is constructed only when `MODEL_API_KEY` is set and
  `LANDERS_REAL_CALLS=1`, both exported by the person.
- Every call goes through one ledger: per model, a count of calls and of tokens or images, a hard cap, and
  a running cost estimate, written to `out/ledger.json`. Caps to start: SAM 3,000 images, Wonder 300 calls,
  Spark 200 turns; `LANDERS_CAP_<MODEL>` overrides. The ledger refuses a call past the cap; nothing else may.
- Prices for the estimate: SAM $2.50 per 1,000 images. Wonder $4 per M input tokens, $20 per M output, about
  1,300 to 1,500 tokens per 1280 px image, so a vote with 256 and 512 px crops at low effort is about $0.02.
  Spark 1.3 $1.25 per M input, $4.25 per M output. The `-contributor` variants are cheaper because the data
  is used by Meta; do not use them. Prompt caching is automatic prefix caching; keep the fixed part of a
  prompt first.
- Rate limits: 429s were reported for Wonder at launch. Retry with backoff, at most three attempts, and
  count the attempt in the ledger either way. 400 means the request shape is wrong; do not retry it.

## SAM 3.1 (model id `sam-3.1`): masks for the size and shape tests

Responses API, streamed. One request per image. The image goes in as a base64 data URL (PNG). Grayscale is
undocumented, so send three identical channels. Images are resized to 1008 px internally, so a 1024 px
tile needs no tiling; a 256 or 512 px crop around a candidate is fine.

Request (`client.responses.create`):

```json
{"model": "sam-3.1", "stream": true,
 "input": [{"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "<prompt>"},
    {"type": "input_image", "image_url": "data:image/png;base64,..."}]}],
 "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"}}
```

Two kinds of prompt, never mixed in one request (mixing returns 400):

- A noun phrase: one short phrase, one concept per request ("bright object"). Text prompts collapse on small
  out-of-domain objects (remote-sensing one-shot mAP 11.7 by text against 66.6 by box), so this pipeline
  uses boxes.
- Box and point prompts, written as tokens inside the same `input_text` string, pixel coordinates, `x2`
  and `y2` inclusive, `w` and `h` the image size repeated on every token, objects separated by commas, up
  to 16 objects, one box per object: `<0f>1<|box;x1=100;y1=120;x2=140;y2=160;w=512;h=512|>`. A positive
  point is `<|point;x=;y=;w=;h=|>`, a negative point has `-` before it. `build_object_prompt` in the
  `meta-sam-parser` package (pip, 0.1.0) builds the string. Box prompts always return `one_bit` masks.
  `include_confidence` must be the string `"true"`, not a boolean; each record then carries `c` in 0 to 1.

Response: one `output_text` lane, one line per frame (`<0f>` for an image), each record an object id, a
box token `<|box;x1=;y1=;x2=;y2=;w=;h=;c=|>` and a mask token `<|mask;x=0;y=0;c=;data=H,W,!payload|>`
(base85 payload; `H` rows then `W` columns; the mask is smaller than the image and is scaled to it). Zero
matches is a completed stream with empty text, not an error. Do not parse the grammar by hand: use
`parse_responses_stream(events, image_segmentation_format()).final_result()` from `meta_sam_parser`, whose
records have `kind` ("box" or "mask"), `object_id`, the box, and `decode_mask_to_raster(record.mask)`
giving a row-major 0/1 array of H by W. The cookbook's `07_sam/01_api_basics/python/sam_api.py` is the
reference streaming wrapper; note it synthesises `response.output_text.done` from
`response.content_part.done`, which the API does not send.

What the pipeline does with it: for each surviving candidate, a box prompt from the detector's blob (padded
by its own size), the returned mask's area, major and minor axes and edge contrast feed the size and shape
tests. SAM supplies measurements, never a verdict. No candidate is promoted because SAM found a mask.

## Muse Wonder (model id `muse-wonder-1.0`): advisory votes on blind crops

Chat Completions with image parts. Images go in user messages only (an image in a developer or system
message returns 400), up to 50 per request, as data URLs.

```json
{"model": "muse-wonder-1.0", "reasoning_effort": "low",
 "messages": [{"role": "user", "content": [
    {"type": "text", "text": "<question>"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]}],
 "response_format": {"type": "json_schema", "json_schema": {"name": "vote", "schema": {...}}}}
```

Structured output is constrained decoding against the schema: `additionalProperties: false`, every field
in `required`, depth at most 10, no recursion. The vote schema: `verdict` in {hardware, natural, unsure},
`confidence` in 0 to 1, `reason` as one sentence. Three votes per candidate on three augmentations.
Perception grounding (points, boxes, counts on a 0 to 1000 grid) exists and is not needed here.

Blind crops: no filename, id, coordinate, date or site name in the prompt or the image; random crop
offsets, flips and a re-stretch per vote; the crop is a square at native resolution plus a 4x zoom; a
reference crop of similar ground from another site is included and labelled only as "reference". The
recognition probe runs first and separately: the same crops with the question "do you recognise this
place or what it shows", recorded on the board; a yes on a famous site is reported, and the advisory
votes are read in that light. Votes are recorded and shown; a vote can lower a grade, never raise one.

## Muse Spark (model id `muse-spark-1.3`): the reviewer agent

Chat Completions with function tools, `reasoning_effort` medium, parallel tool calls allowed, `tool_choice`
auto only. The loop is the standard one: send messages and tools; when the reply has `tool_calls`, append
the assistant message itself, then one `{"role": "tool", "tool_call_id": ..., "content": ...}` per call,
then call again; stop when the reply has no tool calls or the turn cap is hit. Sending a tool result
without first replaying the assistant message returns 400. `reasoning_content` comes back in the
message's extra fields and is logged, not shown on the board.

Spark never sees pixels. Its tools read the structured evidence and nothing else:

- `list_candidates(strip_key)`: ids, grades, test results, persistence, SAM measurements, Wonder votes.
- `get_candidate(id)`: the full evidence record.
- `read_thresholds()`: `controls/thresholds.json` as is.
- `request_check(id, kind)`: one of a fixed menu (zoom pass, second-date check, three more votes); bounded
  by the ledger; the result comes back as evidence.
- `record_verdict(id, action, cites, reason)`: `action` is keep or lower, never raise; `cites` lists the
  evidence fields the reason rests on; a verdict that cites nothing is rejected and the tool says why.

The final answer uses `response_format` with a strict schema: per candidate, action and cited evidence.
Every number in a verdict is copied from the evidence record; the tool log is the audit trail and goes
beside the board.

## The fake backend, and the leak test

One interface for all three models, two implementations: `real` (the SDK, gated as above) and `fake`
(in-process, deterministic: SAM returns a disc mask inside the box with confidence 0.9; Wonder returns a
fixed vote; Spark runs a scripted sequence of tool calls ending in one verdict). A third, `recorded`,
replays saved real responses by request hash once there are any. All tests run on `fake` with no network.
A dry-run mode writes every request that would be sent to `out/model_requests/` without sending it.

The leak test is a unit test and a runtime assertion: no request body, image name or prompt contains an
observation id pattern, a latitude or longitude, a date or a site name from `controls/sites.json`. The
request builder refuses to build one that does.

## As built (plan item 9, blind; docs/reports/2026-10-28-model-layer.md)

The layer lives in `landers/models/`: `leak` (the guard), `ledger`, `backend` (requests, results, the four
backends and the `ModelClient` that every call goes through), `sam`, `crops`, `wonder`, `spark`, `run` (the
passes, written against a pixel reader so the tests run on arrays). The scripts are `scripts/models_sam.py`,
`scripts/models_wonder.py` (`--probe` for the recognition probe) and `scripts/models_review.py`, each with
`--backend fake|dry-run|recorded|real`, writing under `out/models/` with the ledger at `out/models/ledger.json`.

Decisions taken while building, and what the first real run (9b) must check:

- The `openai` and `meta-sam-parser` packages are not dependencies yet; this item ran with no network. The
  real backend imports them lazily and says what to install. Before 9b a person runs
  `uv add openai meta-sam-parser` (network) with the key exported.
- The box-prompt string is built in `landers.models.sam.build_object_prompt` from the grammar above
  (`<0f>` then `<id><box token>` per object, comma separated). The dry-run backend writes the exact
  string; 9b's first SAM call confirms the separator and the `<0f>` prefix, and the result is parsed only
  through `meta_sam_parser`. The record attribute names used in `RealBackend.sam` (`kind`, `object_id`,
  `box`, `mask`) are from this document and are the first thing to check against a real response.
- Structured outputs are sent as `response_format.json_schema` with `strict: true`; if the API returns 400
  on that key, drop it (the schemas already have `additionalProperties: false` and full `required`).
- The real backend is always wrapped in the recorded backend, so every paid response is saved under
  `out/models/model_recordings/` by request hash and a rerun costs nothing.
- The leak guard's published-coordinate rule applies to values with three or more decimals. A two-decimal
  value (1 km precision) collides with ordinary measurements too often to abort a run on, and alone it
  locates nothing; `scripts/leakcheck.sh` keeps the stricter rule for committed files.
- Candidate ids in prompts are `c000`, `c001`, ... by rank; strips are `strip_a`. The mapping to pixel
  positions is a manifest under `out/models/`, never committed and never sent.
- The SAM tests' size limits are the detector's per-branch ranges; the two new limits (elongation, edge
  contrast) are proposed in `docs/proposals/sam-tests-v0.md` and wait for a person.
- Votes lower a grade one step when at least two of three say natural at confidence 0.7 or more and none
  says hardware at that confidence (`landers.models.wonder.VoteRule`, recorded with every vote record).
  Spark's `record_verdict` rejects a raise, an empty citation, a cited field that does not exist, a number
  not present in the evidence record, and the words discovered, confirmed and proven.
