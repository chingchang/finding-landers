#!/bin/bash
# fetch_one.sh <case> <id> <urlbase>  : downloads <urlbase>.LBL and <urlbase>.JP2 into strips/<case>/, resumable
case="$1"; id="$2"; base="$3"
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/download.log"
dir="$ROOT/strips/$case"; mkdir -p "$dir"
for ext in LBL JP2; do
  out="$dir/${id}_RED.$ext"
  [ -f "$out.done" ] && continue
  ok=0
  for try in 1 2 3 4 5; do
    if curl -sS -L -C - --retry 3 --retry-delay 10 -o "$out" "$base.$ext"; then
      touch "$out.done"; echo "$(date '+%m-%d %H:%M:%S') ok   $case $id .$ext $(du -h "$out" | cut -f1)" >> "$LOG"; ok=1; break
    fi
    echo "$(date '+%m-%d %H:%M:%S') retry$try $case $id .$ext" >> "$LOG"; sleep 20
  done
  [ $ok = 1 ] || echo "$(date '+%m-%d %H:%M:%S') FAIL $case $id .$ext" >> "$LOG"
done
