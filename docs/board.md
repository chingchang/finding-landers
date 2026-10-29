# The case board

One static HTML page per run, built from results files only. It runs no detector, no registration and no
model; it reads what the other stages wrote and lays it out in the fixed vocabulary, with every value tagged
with the file and the JSON path it was copied from.

```
uv run scripts/board.py out/<run>/candidates_<run>.json            # persist_*.json beside it, models under out/models
uv run scripts/board.py <candidates.json> --score out/<run>/score_<run>.json --coverage out/search/coverage.json
uv run scripts/board.py <candidates.json> --blind --out out/board/blind.html
uv run scripts/board.py --demo out/board_demo                      # fake backend; results files and page together
```

Outputs: the page and `<page>_trace.json` beside it, a list of every value on the page with its source file,
path and the file's hash.

## What it reads

| file | written by | what the board takes from it |
|---|---|---|
| `candidates_<run>.json` | `scripts/detect.py` | run, detector version, commit; per strip the valid area, scale, tiles, every candidate's row, col, score, branch, grade, area, shape features, physical tests when present |
| `persist_<name>.json` | `scripts/persist.py` | per direction the registration summary, counts, inject check; per candidate `extra.persist` and the grade after persistence |
| `sam_<strip>.json` | `scripts/models_sam.py` | per candidate the mask (returned or not), confidence, measurements, the size, shape and edge test outcomes |
| `probe_<strip>.json` | `scripts/models_wonder.py --probe` | per candidate how many crops were asked and how many answers recognised the place, with the model's claims verbatim |
| `votes_<strip>.json` | `scripts/models_wonder.py` | per candidate three votes with confidence and reason, the grade before and after the votes |
| `review_<strip>.json` | `scripts/models_review.py` | per candidate the verdict, its citations and reason, the grade before and after review; the checks ordered; turns, how the loop stopped, tool-call counts |
| `manifest_<strip>.json` | the model scripts | checked against the rank order; a disagreement unjoins the model files and says so on the page |
| `ledger.json` | `landers.models.ledger` | per model units, cap, attempts, outcomes, tokens and the cost estimate |
| `coverage.json` | item 11a (`scripts/search.py`) | rendered as it is, whatever its shape; a `coverage.png` beside it is shown |
| `score_*.json` | `scripts/score.py` | the headline, the pieces and the strips (not on the blind page: it names sites) |

Candidate ids are the model scripts' `c000`, `c001`, ... by rank in the score-sorted list of the candidates
file. The page shows the top `--top` (default 50) per strip, or more when the model files cover more.

## The grade chain

Each candidate carries the grade every stage ended at: detector, persistence, votes, review. The final grade
is the lowest of them; a stage can lower and never raise, and the page flags, in red, a file in which a grade
went up and a stage whose starting grade is not the previous stage's ending grade. The second flag is on
every demo candidate, and will be on real ones until the model scripts are fed the list persistence wrote:
today `scripts/models_*.py` read a candidates file, whose grades are the detector's, while the grade after
persistence lives in `persist_<name>.json`. That is a pipeline gap the board makes visible, not something it
papers over.

## Tracing

`landers.board.load.Source.get(*path)` is the only way a value enters the case, and `Source.count(*path)`
the only way a number is made; the renderer writes each as
`<span class="n" data-src="<file key>" data-path='<json path>' data-op="">value</span>` and into the trace
file. `tests/test_board.py` reads the page back and checks that no digit sits outside such a span (candidate
ids excepted) and that every span's text equals the value at that path in that file. Counts carry
`data-op="count"` (or `count where ...` with the condition stated); the rank carries `rank by score`;
dict keys with digits in them (a histogram bin, a strip id) are traced as `key`.

Model text (vote reasons, verdict reasons, probe claims) is shown verbatim inside `<q class="model">`,
labelled as the model's words. The page's own words never include found, discovered, confirmed or proven; a
test checks that too.

## The blind page

`--blind` replaces strip ids with `strip_a`, `strip_b`, ... and persistence file keys with `persist:a`, ...
in every string, drops pixel positions, file paths, the ledger's start time and the score section, then runs
`landers.models.leak` over the page and the trace and fails if anything is left. It is the page that can be
published; the open page stays under `out/`.

## The demo

`landers.board.demo.build` writes a complete set of results files from two squares of synthetic ground with
bright and dark discs: detector-shaped candidates, persistence by identity (the second square lacks one
object), the SAM, probe, vote and review files from the fake backend with their ledger, and a small
coverage file. Nothing in it is about Mars; it is what the tests run on and what a person can open before
the first real run (`out/board_demo/board/index.html` after `--demo out/board_demo`).
