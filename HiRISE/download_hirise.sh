#!/bin/bash
# Usage: ./download_hirise.sh [case-regex]   e.g. ./download_hirise.sh 'control|mpl'   (default: everything)
# Resumable; 3 parallel downloads; progress in download.log; finished files get a .done marker.
ROOT="$(cd "$(dirname "$0")" && pwd)"
FILTER="${1:-.}"
chmod +x "$ROOT/fetch_one.sh"
echo "$(date) start filter=$FILTER" >> "$ROOT/download.log"
grep -E "^($FILTER)" "$ROOT/manifest.txt" | xargs -P 3 -L 1 "$ROOT/fetch_one.sh"
echo "$(date) finished" >> "$ROOT/download.log"
