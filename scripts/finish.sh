#!/bin/bash
# Runs the named plan items in order with no one at the keyboard, then stops. Usage:
#   scripts/finish.sh 17b 17c 17d          (an item already marked [done] is skipped)
# If an autopilot is running here, it is told to stop after its current item, and this waits for it first,
# so two agents never share the folder. Each item goes through scripts/run_plan.sh (network and usage-limit
# recovery, the checks after each item). It stops early only if an item ends without being marked [done].
# With FINAL_MERGE=1 the branch is merged into the main checkout at the end.
set -u
cd "$(dirname "$0")/.."
Q=out/queue; mkdir -p "$Q"
if [ -f "$Q/autopilot.pid" ] && kill -0 "$(cat "$Q/autopilot.pid")" 2>/dev/null; then
  touch "$Q/STOP"; echo "$(date '+%F %T') waiting for the running autopilot to finish its current item"
  while kill -0 "$(cat "$Q/autopilot.pid")" 2>/dev/null; do sleep 60; done
fi
rm -f "$Q/next"
for it in "$@"; do
  if grep -qE "^\s*${it}\. \[done" docs/plan.md; then echo "$it already done"; continue; fi
  echo "$(date '+%F %T') item $it"
  ITEM="$it" ITEM_USD="${ITEM_USD:-30}" ITEM_TURNS="${ITEM_TURNS:-400}" scripts/run_plan.sh >> "$Q/finish.log" 2>&1
  rc=$?
  git merge --no-edit main >/dev/null 2>&1 || true
  if ! grep -qE "^\s*${it}\. \[done" docs/plan.md; then
    echo "$(date '+%F %T') item $it ended without [done] (exit $rc); stopping. See $Q/finish.log"; exit 1
  fi
done
if [ "${FINAL_MERGE:-}" = 1 ]; then
  MAIN="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"; BR="$(git branch --show-current)"
  git -C "$MAIN" merge --no-ff --no-edit "$BR" && echo "merged $BR into the main checkout"
fi
echo "$(date '+%F %T') all items done"
