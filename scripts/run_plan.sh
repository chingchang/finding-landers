#!/bin/bash
# Runs the plan unattended: one fresh Claude Code session per open item in docs/plan.md, until the items run
# out, something needs a person, or the cap is hit. Start it in Terminal before you leave:
#
#   cd ~/finding-landers/.claude/worktrees/repo-overview-plan-e248f3   # the agent's worktree
#   caffeinate -i scripts/run_plan.sh 6        # at most 6 items; caffeinate keeps the Mac awake
#   ITEM=9 caffeinate -i scripts/run_plan.sh   # one named item, for a second worktree running in parallel
#
# Stops on: a red check, an item the agent marked [blocked] (needs a person), a refused tier-1 change, or the
# item cap. Nothing is pushed. Each item lands as a commit on the branch with a report under docs/reports/.
set -euo pipefail
cd "$(dirname "$0")/.."
MAX_ITEMS="${1:-6}"
ITEM="${ITEM:-}"              # ITEM=9 scripts/run_plan.sh  runs only that item (for a second worktree)
if [ -n "$ITEM" ]; then MAX_ITEMS=1; PICK="item $ITEM under Now; it may be marked [ ] or [running] (an earlier session ended before finishing; continue from the branch's state); if it is marked [done] or [blocked, stop"
else PICK="the first item under Now marked [running] if there is one (an earlier session ended before finishing it; continue from the branch's state), otherwise the first item marked [ ]"; fi
# Long runs. A background shell does not survive the session's end (5 s grace in -p mode), so background
# tasks are off and a foreground command may run for up to two hours.
export CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1
export BASH_DEFAULT_TIMEOUT_MS="${BASH_DEFAULT_TIMEOUT_MS:-3600000}"
export BASH_MAX_TIMEOUT_MS="${BASH_MAX_TIMEOUT_MS:-7200000}"
ITEM_TURNS="${ITEM_TURNS:-200}"
ITEM_USD="${ITEM_USD:-15}"
mkdir -p out/plan_runs
TOOLS='Read,Edit,Write,Grep,Glob,Bash(uv run *),Bash(uv sync*),Bash(python3 *),Bash(scripts/*),Bash(git status*),Bash(git diff*),Bash(git log*),Bash(git add *),Bash(git commit *),Bash(git merge main*),Bash(git merge --no-edit main*),Bash(ls *),Bash(mkdir *),Bash(wc *),Bash(cat *),Bash(head *),Bash(tail *)'

for i in $(seq 1 "$MAX_ITEMS"); do
  stamp=$(date +%Y%m%d-%H%M%S)
  if ! grep -qE '^\s*[0-9]+b?\. \[( |running)\]' docs/plan.md; then echo "no open items in docs/plan.md"; exit 0; fi
  if grep -qiE '\[blocked' docs/plan.md; then echo "an item is marked blocked; needs a person"; exit 3; fi
  prompt="No human is watching. Merge main into this branch first (git merge --no-edit main). Then read CLAUDE.md
and docs/plan.md, and take $PICK. If it is item 3 (the key) or
anything that needs a person (money, a push, a frozen tag, a tier-1 file), mark it [blocked: reason] and stop.
Otherwise mark it [running], do it, make scripts/leakcheck.sh and the tests green, commit on this branch with
a message starting with the item number, write the report under docs/reports/, mark the item [done], and stop.
Do only that one item. Do not push. A long computation (a detector pass over the strips) runs in the
foreground with a timeout of up to two hours and you wait for it; background runs are disabled here because
the session's end would kill them. If a run would take longer than that, split it per strip and commit the
code and each strip's result as it lands, so a later session can continue."
  echo "== item run $i ($stamp)"
  if ! claude -p "$prompt" --permission-mode acceptEdits --permission-prompts none \
       --allowedTools "$TOOLS" --max-turns "$ITEM_TURNS" --max-budget-usd "$ITEM_USD" \
       --output-format json > "out/plan_runs/$stamp.json"; then
    echo "session ended non-zero (cap or error); see out/plan_runs/$stamp.json"; exit 2
  fi
  if ! (uv run pytest -q >/dev/null 2>&1 && scripts/leakcheck.sh >/dev/null 2>&1); then
    echo "check is red after the session; stopping"; exit 4
  fi
done
echo "item cap reached"
