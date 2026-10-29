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
#
# Interruptions. A laptop that moves loses its network, and the session dies with an API error. The script
# then waits for api.anthropic.com to answer again and resumes the same session (the agent keeps its context),
# up to RETRIES times per item. A usage limit is handled the same way with a LIMIT_WAIT_MIN pause between
# tries. The model: out/queue/model holding one line (opus, sonnet, or a full model id) puts every later
# session and retry on that model; no file means the account's default. MODEL=... in the environment wins.
# A new run of an item first resumes the newest session if it died that way, even one an older copy started.
set -euo pipefail
# Run from a private copy: a merge that rewrites this file while a session is running must not reach the
# running script (bash reads a script as it goes).
if [ -z "${RUN_PLAN_SELF:-}" ]; then
  cd "$(dirname "$0")/.."
  t="$(mktemp "${TMPDIR:-/tmp}/run_plan.XXXXXX")"; cp "$0" "$t"
  RUN_PLAN_SELF=1 exec bash "$t" "$@"
fi
MAX_ITEMS="${1:-6}"
ITEM="${ITEM:-}"              # ITEM=9 scripts/run_plan.sh  runs only that item (for a second worktree)
if [ -n "$ITEM" ]; then MAX_ITEMS=1; PICK="item $ITEM under Now; it may be marked [ ] or [running] (an earlier session ended before finishing; continue from the branch's state); if it is marked [done] or [blocked, stop"
else PICK="the first item under Now marked [running] if there is one (an earlier session ended before finishing it; continue from the branch's state), otherwise the first item marked [ ]"; fi
# Long runs. A background shell does not survive the session's end (5 s grace in -p mode), so background
# tasks are off and a foreground command may run for up to two hours.
export CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1
export BASH_DEFAULT_TIMEOUT_MS="${BASH_DEFAULT_TIMEOUT_MS:-3600000}"
export BASH_MAX_TIMEOUT_MS="${BASH_MAX_TIMEOUT_MS:-7200000}"
# A worktree has no HiRISE/ of its own: point the data layer at the main checkout's unless already set.
COMMON="$(git rev-parse --git-common-dir 2>/dev/null || true)"; [ -n "$COMMON" ] && export LANDERS_DATA="${LANDERS_DATA:-$(cd "$COMMON/.." && pwd)/HiRISE}"
ITEM_TURNS="${ITEM_TURNS:-200}"
ITEM_USD="${ITEM_USD:-15}"
RETRIES="${RETRIES:-8}"             # resumes per item after a network drop or a usage limit
NET_WAIT_MIN="${NET_WAIT_MIN:-240}" # how long to wait for the network before giving up
LIMIT_WAIT_MIN="${LIMIT_WAIT_MIN:-20}"
mkdir -p out/plan_runs out/queue
TOOLS='Read,Edit,Write,Grep,Glob,Bash(uv run *),Bash(uv sync*),Bash(python3 *),Bash(scripts/*),Bash(git status*),Bash(git diff*),Bash(git log*),Bash(git add *),Bash(git commit *),Bash(git merge main*),Bash(git merge --no-edit main*),Bash(ls *),Bash(mkdir *),Bash(wc *),Bash(cat *),Bash(head *),Bash(tail *)'

pick_model() {  # sets MNAME and MARGS (--model X) when a model is chosen: the environment first, then out/queue/model
  MNAME="${MODEL:-}"; MARGS=()
  [ -z "$MNAME" ] && [ -f out/queue/model ] && MNAME="$(head -1 out/queue/model | tr -d '[:space:]')"
  [ -n "$MNAME" ] && MARGS=(--model "$MNAME"); return 0
}
run_kind() {  # network | limit | other, from a session's json (an empty file means the process was killed)
  python3 - "$1" <<'PY'
import json, re, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("network"); sys.exit()
s = ((d.get("result") or "") + " " + str(d.get("subtype") or "")).lower()
if re.search(r"can't reach the api server|enotfound|econnreset|econnrefused|etimedout|fetch failed|socket hang up|network error|connection error", s):
    print("network")
elif re.search(r"usage limit|limit reached|hit your limit|rate limit|too many requests|overloaded|\b429\b|\b529\b", s):
    print("limit")
else:
    print("other")
PY
}
session_of() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("session_id") or "")' "$1" 2>/dev/null || true; }
is_error() { python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("is_error") else 1)' "$1" 2>/dev/null; }
wait_for_network() {  # returns when api.anthropic.com answers (DNS, TCP and TLS all up); false after NET_WAIT_MIN
  local end=$(( $(date +%s) + 60 * NET_WAIT_MIN ))
  until curl -sS -m 10 -o /dev/null https://api.anthropic.com/ 2>/dev/null; do
    [ "$(date +%s)" -ge "$end" ] && return 1
    sleep 20
  done
  sleep 30   # let the connection settle before the first call
}

for i in $(seq 1 "$MAX_ITEMS"); do
  if ! grep -qE '^\s*[0-9]+[a-z]?\. \[( |running)\]' docs/plan.md; then echo "no open items in docs/plan.md"; exit 0; fi
  if grep -qiE '\[blocked' docs/plan.md; then echo "an item is marked blocked; needs a person"; exit 3; fi
  prompt="No human is watching. Merge main into this branch first (git merge --no-edit main); if git refuses
because of uncommitted changes left by an earlier session, commit them first as work in progress (git add -A;
git commit -m 'wip: carried over from a session that ended early'), then merge. Then read CLAUDE.md
and docs/plan.md, and take $PICK. If it is item 3 (the key) or
anything that needs a person (money, a push, a frozen tag, a tier-1 file), mark it [blocked: reason] and stop.
Otherwise mark it [running], do it, make scripts/leakcheck.sh and the tests green, commit on this branch with
a message starting with the item number, write the report under docs/reports/, mark the item [done], and stop.
Do only that one item. Do not push. A long computation (a detector pass over the strips) runs in the
foreground with a timeout of up to two hours and you wait for it; background runs are disabled here because
the session's end would kill them. If a run would take longer than that, split it per strip and commit the
code and each strip's result as it lands, so a later session can continue. This machine sometimes loses its
network for a while; the session is then resumed automatically, but a command that was running at that
moment is killed, so start long passes with their --resume option where the script offers one, and have
scripts write each strip's or tile's result as it lands."
  resume_prompt="This session was interrupted (the machine lost its network, or the account's usage limit
paused it) and has been resumed; an API error above is that interruption, not something you did. No human
is watching. A command that was running at that moment was killed. Check git status and the files under
out/ for what finished, re-run only what was cut off (use --resume where the script offers it), then
continue the item from where you left off and finish as instructed before."
  resume=""; attempt=0
  # A session that died on a network drop or a usage limit (including one started by an older copy of this
  # script) is resumed rather than replaced, so the agent continues from its last step instead of re-reading
  # the repo: the newest session file, if it ended in such an error within the last 12 hours and has an id.
  last="$(ls out/plan_runs/*.json 2>/dev/null | sort | tail -1 || true)"
  if [ -n "$last" ] && [ -s "$last" ] && is_error "$last" && [ -n "$(find "$last" -mmin -720 2>/dev/null)" ]; then
    k="$(run_kind "$last")"; sid="$(session_of "$last")"
    if [ "$k" != other ] && [ -n "$sid" ]; then
      resume="$sid"; echo "resuming session $sid, which ended on a $k error ($last)"
      [ "$k" = network ] && { wait_for_network || { echo "no network for $NET_WAIT_MIN minutes"; exit 2; }; }
    fi
  fi
  while :; do
    stamp=$(date +%Y%m%d-%H%M%S); f="out/plan_runs/$stamp.json"
    pick_model
    if [ -n "$resume" ]; then
      echo "== item run $i, resume $attempt of session $resume ($stamp)${MNAME:+, model $MNAME}"
      set +e; claude -p "$resume_prompt" --resume "$resume" ${MARGS[@]+"${MARGS[@]}"} --permission-mode acceptEdits --permission-prompts none \
        --allowedTools "$TOOLS" --max-turns "$ITEM_TURNS" --max-budget-usd "$ITEM_USD" --output-format json > "$f"; rc=$?; set -e
    else
      echo "== item run $i ($stamp)${MNAME:+, model $MNAME}"
      set +e; claude -p "$prompt" ${MARGS[@]+"${MARGS[@]}"} --permission-mode acceptEdits --permission-prompts none \
        --allowedTools "$TOOLS" --max-turns "$ITEM_TURNS" --max-budget-usd "$ITEM_USD" --output-format json > "$f"; rc=$?; set -e
    fi
    if [ "$rc" -eq 0 ] && ! is_error "$f"; then break; fi
    kind="$(run_kind "$f")"; resume="$(session_of "$f")"   # no session id (process killed): a fresh session instead
    attempt=$((attempt + 1))
    if [ "$kind" = other ] || [ "$attempt" -gt "$RETRIES" ]; then
      echo "session ended non-zero ($kind; cap or error); see $f"; exit 2
    fi
    if [ "$kind" = network ]; then
      echo "$(date '+%F %T') session lost the network; waiting for it to come back"
      wait_for_network || { echo "no network for $NET_WAIT_MIN minutes; giving up on this item"; exit 2; }
    else
      echo "$(date '+%F %T') usage limit; waiting $LIMIT_WAIT_MIN minutes (out/queue/model switches the model)"
      sleep $((60 * LIMIT_WAIT_MIN))
    fi
  done
  if ! (uv run pytest -q >/dev/null 2>&1 && scripts/leakcheck.sh >/dev/null 2>&1); then
    echo "check is red after the session; stopping"; exit 4
  fi
done
echo "item cap reached"
