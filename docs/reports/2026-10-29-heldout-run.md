# Item 10: held-out run (detector only, not scored)

What ran. The detector at frozen-v1, once, over the strips of the `heldout` group (three sites) and then, as a
separate run, over the strips of the `final_exam` group (Beagle 2), as listed in controls/sites.json. Nothing
was scored. controls/heldout.json was not opened by the agent. No model was called.

Code state. The runs were made at commit f24fae0. `git diff frozen-v1^{commit} HEAD -- landers scripts/detect.py
controls/thresholds.json pyproject.toml uv.lock` is empty, so the code that ran is the frozen code (4f4253e). The
candidate files record `"frozen": true`, detector v0.4, `calibration_mode: table` with
landers/calibration_v0.json, and landers/shape_v3.json (copied from the files' `detector` field).

Commands (from out/heldout_v1/run.log):

    uv run --env-file out/landers.env scripts/detect.py --site <A> --site <B> --site <C> \
        --frozen --jobs 3 --run heldout_v1 --out out/heldout_v1 --resume
    uv run --env-file out/landers.env scripts/detect.py --site <D> \
        --frozen --jobs 3 --run final_exam_v1 --out out/heldout_v1 --resume

A, B and C are the three `heldout` sites of controls/sites.json, in file order, and D is the `final_exam` site; the exact command is in
out/heldout_v1/run.log. Each ran once, start to finish, with no interruption (neither file has a `resumed_from` field).

| run | strips | tiles | candidates | started | file written |
|---|---|---|---|---|---|
| heldout_v1 | 3 | 661 | 202,296 | 17:38:59 | 17:58:10 |
| final_exam_v1 | 3 | 909 | 182,177 | 17:58:15 | 18:26:39 |

Tiles and candidates per strip are in out/heldout_v1/run.log and in each file's `strips` entries; the totals
above are their sums. Times are the files' `started` field and their modification time. The held-out strips are
not named here, by the rule that keeps sealed-site names out of committed text; they are the `heldout` group's
strips in controls/sites.json.

Outputs (git-ignored, as out/baseline_v1/ is):

- out/heldout_v1/candidates_heldout_v1.json (three held-out sites)
- out/heldout_v1/candidates_final_exam_v1.json (Beagle 2, three strips)
- out/heldout_v1/run.log, out/heldout_v1/COMMIT

Decisions.

- Two files, not one. score.py scores only the pieces whose strip is in the candidates file, so the person can
  score the three sites and Beagle 2 as two separate, single events, in the order the plan gives.
- `--resume` on both, so a dropped session could have continued from the finished strips; it was not needed.
- One gap: the per-strip times of the first two Beagle 2 strips were cut from the captured output; the run's
  total time is known from the file times.

For the person. Score each file once:

    uv run scripts/score.py out/heldout_v1/candidates_heldout_v1.json --heldout
    uv run scripts/score.py out/heldout_v1/candidates_final_exam_v1.json --heldout

A miss at Beagle 2 is a reported result. The agent has not seen either score.

Next. Item 11, the search, on the same frozen detector; the model calls on its survivors wait for a person.
