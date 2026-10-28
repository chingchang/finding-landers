#!/bin/bash
# Fails when code, prompts, scripts or committed outputs contain anything that says which image or site
# they came from: any HiRISE observation id, or the published coordinates or names of the held-out and
# final-exam sites. docs/data.md and the controls files are allowed to name them; results and code are not.
#
#   scripts/leakcheck.sh            exit 0 when clean, 1 with a listing when not
#   LEAKCHECK_SITES=path            controls/sites.json (default <repo>/controls/sites.json)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITES="${LEAKCHECK_SITES:-$ROOT/controls/sites.json}"
[ -f "$SITES" ] || { echo "leakcheck: no sites file at $SITES" >&2; exit 2; }

CODE_PATHS=()
for d in landers prompts scripts experiments; do [ -d "$ROOT/$d" ] && CODE_PATHS+=("$ROOT/$d"); done
RESULT_PATHS=()
[ -d "$ROOT/out/committed" ] && RESULT_PATHS+=("$ROOT/out/committed")
for f in "$ROOT"/docs/results*.md "$ROOT"/docs/report*.md; do [ -f "$f" ] && RESULT_PATHS+=("$f"); done

fail=0
report() { echo "LEAK ($1):"; echo "$2" | sed 's/^/  /'; fail=1; }

# 1. Observation ids anywhere in code or results.
hits=$(grep -rnE --exclude-dir=__pycache__ --exclude=leakcheck.sh '\b(ESP|PSP)_[0-9]{6}_[0-9]{4}\b' "${CODE_PATHS[@]}" ${RESULT_PATHS[@]+"${RESULT_PATHS[@]}"} 2>/dev/null)
[ -n "$hits" ] && report "observation id in code or results" "$hits"

# 2. Published coordinates and names of sealed sites (heldout, final_exam), from sites.json.
while IFS=$'\t' read -r name lat lon; do
  for v in "$lat" "$lon"; do
    pat="(^|[^0-9.])${v//./\\.}([^0-9]|$)"
    hits=$(grep -rnE --exclude-dir=__pycache__ "$pat" "${CODE_PATHS[@]}" ${RESULT_PATHS[@]+"${RESULT_PATHS[@]}"} 2>/dev/null)
    [ -n "$hits" ] && report "coordinate $v of sealed site $name" "$hits"
  done
  hits=$(grep -rniE --exclude-dir=__pycache__ "\b${name}\b" "${CODE_PATHS[@]}" ${RESULT_PATHS[@]+"${RESULT_PATHS[@]}"} 2>/dev/null)
  [ -n "$hits" ] && report "name of sealed site $name" "$hits"
done < <(python3 -I -c '
import json,sys
for s in json.load(open(sys.argv[1]))["sites"]:
    if s["group"] in ("heldout","final_exam"):
        print(s["name"], s["lat"], s["lon_e"], sep="\t")' "$SITES")

if [ $fail = 0 ]; then echo "leakcheck: clean"; fi
exit $fail
