# Report: the case board (2026-10-28)

Plan item 12a, branch `claude/model-layer`. Built and tested on the fake backend's outputs; no strip was
read, no model was called, and nothing below is a result about Mars.

## What was built

`landers/board/` (`load`, `render`, `demo`), `scripts/board.py`, `tests/test_board.py`, `docs/board.md`.

- **Loading** (`load.py`). The candidates file, the persistence files beside it, the model files under
  `out/models/` (SAM, probe, votes, review, manifest, ledger), a coverage file of any shape and an optional
  score file, joined into one case. A value enters the case only through `Source.get(path)`, which reads it
  from a loaded file, or `Source.count(path)`, which counts a list in one; there is no third way, so every
  value on the page has a file and a path by construction. Candidate ids follow the model scripts (rank in
  the score-sorted list); the manifest is checked against that order and a disagreement unjoins the model
  files and is printed on the page. A persistence file whose candidate rows do not match the candidates file
  is refused. Every grade, outcome, vote and action read from a file is checked against the fixed vocabulary
  and a word outside it stops the build.
- **The grade chain.** Per candidate: the grade the detector gave, after persistence, after the votes, after
  review. The final grade is the lowest of them. A file in which a grade went up is flagged in red and not
  believed; so is a stage whose starting grade is not the previous stage's ending grade.
- **Rendering** (`render.py`). Plain HTML, no script. Each value is a span carrying its source key, JSON
  path and operation (copied, count, count where, rank by score, key, file hash, file path), with the same
  in a trace sidecar. Model text is quoted verbatim and labelled as the model's words. Unknown shapes
  (coverage, registration summaries, ordered checks) go through one generic renderer that traces every
  scalar and every key with a digit in it.
- **The blind page** (`--blind`). Strip ids and persistence file keys replaced by neutral names in every
  string, positions, paths, the ledger's start time and the score section dropped, and the leak guard from
  `landers.models.leak` run over the page and the trace; a leak fails the build.
- **The demo** (`demo.py`, `scripts/board.py --demo DIR`). Two squares of synthetic ground, detector-shaped
  candidates, persistence by identity, the four model files and the ledger from the fake backend, a small
  coverage file; then the page. `out/board_demo/board/index.html` and `blind.html` were built from it here;
  they are under `out/` and not committed.

Tests (`tests/test_board.py`, twelve of them): the demo writes the shapes the scripts write; the join and the
grade chain; every digit on the page is inside a traced span and every span's text equals the value at its
path in its file (checked by re-reading the files, several hundred values); the board's own words contain
none of found, discovered, confirmed, proven; a word outside the vocabulary stops the build; a raised grade
is flagged and the lower grade kept; a persistence file for other candidates is refused; a manifest mismatch
unjoins the model files; the blind page built with realistic-looking ids carries none of them; the score
section; the generic renderer on an arbitrary nested shape; the script end to end. `uv run pytest -q` and
`scripts/leakcheck.sh` are green at this commit; the test count is whatever that command prints.

## What I decided and why

- **Tracing is structural, not a convention.** The first draft had the renderer annotate numbers it was
  handed; it is too easy to hand it a computed one. Making `Source.get` the only constructor of a value, and
  a test that reads the page back against the files, means a future section cannot show an untraced number
  without failing the suite.
- **No sums.** An early version summed the probe's recognised answers over candidates; that is a derived
  number with no path in any file, so it is gone. The page shows the per-candidate values and the only
  arithmetic it does is counting entries of a list, stated as such in the tooltip.
- **The lowest grade wins, and the gap is shown.** On the demo every candidate of the first strip is flagged
  "votes: started from needs second look but persistence ended at candidate": the model scripts read a
  candidates file, whose grades are the detector's, while persistence writes its grades into
  `persist_<name>.json`. The board could have quietly taken the later stage's grade; instead it takes the
  lowest and flags the break, because the rule is that nothing raises and the reader should see where the
  pipeline's bookkeeping does not yet line up.
- **Coverage is rendered generically.** Item 11a is running in another worktree and its file shape is not
  committed yet; the generic renderer shows whatever it writes, traced, and a `coverage.png` beside it.
- **A blind variant rather than a blind-only page.** The person checking claims against pixels needs
  observation ids and row, col; the write-up needs a page with none. Both come from the same case.

## What I would do next

1. Close the grade gap above: have `scripts/persist.py` also write a candidates-shaped file (same keys,
   grades after persistence) or let `scripts/models_*.py` take `--persist`, so the model passes start from
   the persistence grade and the chain is consistent. A small change on the main branch, not this item.
2. When 11a lands, replace the generic coverage section with a specific one if its file has structure worth
   a table (dates per cell as a histogram, valid area per strip), still through `Source.get`.
3. After 9b, build the board on the first real files (`uv run scripts/board.py out/baseline_v1/...
   --models out/models`) and read the flags before anything else; the manifest check and the vocabulary
   check are the two most likely to speak.
