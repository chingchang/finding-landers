"""The case board: one static HTML page built from results files only.

Nothing here runs a detector, a registration or a model. The page shows what the results files say, in the
fixed vocabulary (grades: candidate, needs second look, likely natural, not assessed; test outcomes: pass,
fail, unsure, not run; votes: hardware, natural, unsure; verdicts: keep, lower), and every value on it is
tagged with the file and the JSON path it was copied from, so a reader can open the file and check.

- ``load``: reads the files into one ``Case``. A value can only enter the case by reading a path from a
  loaded file (``Source.get``) or by counting the entries of a list in one (``Source.count``); there is no
  other way to make a number, so the trace is a property of the code, not a convention.
- ``render``: the HTML and a sidecar trace (``board_trace.json``) listing every value with its source.
- ``demo``: a complete set of results files from synthetic ground and the fake backend, no strips, no
  network, no model call; what the tests run on and what a person can look at before the first real run.
"""
