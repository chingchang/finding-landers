#!/bin/bash
# Fails when anything in the repo says which image or sealed site something came from: a HiRISE observation
# id, or the published coordinates or name of a held-out or final-exam site. Scans every file git tracks or
# would track (untracked but not ignored), except the allowlist, which is where those facts legitimately
# live: docs/data.md, controls/, HiRISE/manifest.txt. Reports under docs/reports/ may name observation ids
# (a reproducible report must say which strip a number came from); the sealed-site name and coordinate
# rules apply there too.
#
#   scripts/leakcheck.sh            exit 0 when clean, 1 with a listing when not
#   LEAKCHECK_SITES=path            controls/sites.json (default <repo>/controls/sites.json)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SITES="${LEAKCHECK_SITES:-$ROOT/controls/sites.json}"
[ -f "$SITES" ] || { echo "leakcheck: no sites file at $SITES" >&2; exit 2; }

ALLOW='^(docs/data\.md|controls/.*|HiRISE/manifest\.txt)$'
FILES="$(cd "$ROOT" && { git ls-files; git ls-files -o --exclude-standard; } | sort -u | grep -Ev "$ALLOW" | grep -Ev '\.(png|jpg|jpeg|gif|JP2|jp2|IMG|lock)$')"
[ -n "$FILES" ] || { echo "leakcheck: nothing to scan"; exit 0; }

fail=0
report() { echo "LEAK ($1):"; echo "$2" | sed 's/^/  /'; fail=1; }
scan() { (cd "$ROOT" && echo "$FILES" | tr '\n' '\0' | xargs -0 grep -nE "$@" -- 2>/dev/null); }

# 1. Observation ids, everywhere but the reports.
hits=$(scan '\b(ESP|PSP)_[0-9]{6}_[0-9]{4}\b' | grep -Ev '^docs/reports/')
[ -n "$hits" ] && report "observation id" "$hits"

# 2. Published coordinates and names of sealed sites (heldout, final_exam), from sites.json.
while IFS=$'\t' read -r name lat lon; do
  for v in "$lat" "$lon"; do
    hits=$(scan "(^|[^0-9.])${v//./\\.}([^0-9.]|$)")
    [ -n "$hits" ] && report "coordinate $v of sealed site $name" "$hits"
  done
  hits=$(scan -i "\b${name}\b")
  [ -n "$hits" ] && report "name of sealed site $name" "$hits"
done < <(python3 -I -c '
import json,sys
for s in json.load(open(sys.argv[1]))["sites"]:
    if s["group"] in ("heldout","final_exam"):
        print(s["name"], s["lat"], s["lon_e"], sep="\t")' "$SITES")

if [ $fail = 0 ]; then echo "leakcheck: clean ($(echo "$FILES" | wc -l | tr -d ' ') files)"; fi
exit $fail
