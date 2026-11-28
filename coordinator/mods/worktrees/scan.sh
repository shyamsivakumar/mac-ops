#!/bin/sh
set -u
mode=${1:-scan}
role=${2:-start}
[ $# -gt 0 ] && shift
[ $# -gt 0 ] && shift
case "$mode" in scan | clean) ;; archive | delete) [ $# -gt 0 ] || exit 2 ;; *) exit 2 ;; esac
for target in "$@"; do
  case "$target" in /*) ;; *) exit 2 ;; esac
done
STATE=${WORKTREE_PANEL_STATE:-$HOME/.local/state/herdr-worktrees}
CLEANER=${WORKTREE_CLEANER:-$HOME/Code/mac-ops/scripts/worktree-cleaner/cleaner.py}
CLEANER_STATE=${WORKTREE_CLEANER_STATE:-$HOME/.local/state/mac-ops/worktree-cleaner}
SCAN_LIMIT=${WORKTREE_SCAN_LIMIT:-600}
CLEAN_LIMIT=${WORKTREE_CLEAN_LIMIT:-1800}
ARCHIVE_LIMIT=${WORKTREE_ARCHIVE_LIMIT:-600}
DELETE_PER_ROW=${WORKTREE_DELETE_PER_ROW:-90}
PYTHON=/usr/bin/python3
run_limit=0
[ "$mode" = delete ] && run_limit=$((DELETE_PER_ROW * $#))
LOCK=$STATE/run.lock
umask 077
mkdir -p "$STATE"

record() {
  printf '%s|%s\n' "$1" "$(ps -o lstart= -p "$1" 2> /dev/null)"
}

claim() {
  record "$1" > "$LOCK/pid.tmp"
  mv "$LOCK/pid.tmp" "$LOCK/pid"
}

lock_busy() {
  if [ -f "$LOCK/pid" ]; then
    rec=$(cat "$LOCK/pid")
    [ "$(ps -o lstart= -p "${rec%%|*}" 2> /dev/null)" = "${rec#*|}" ]
  else
    [ -z "$(find "$LOCK" -maxdepth 0 -mmin +1)" ]
  fi
}

status() {
  printf '{"state":"%s","mode":"%s","at":%s,"finished":%s,"limit":%s,"error":"%s"}\n' "$1" "$mode" "$started" "$2" "$run_limit" "$3" > "$STATE/status.tmp"
  mv "$STATE/status.tmp" "$STATE/status.json"
}

reason() {
  text=$(sed -n 's/.*"error": "\([^"]*\)".*/\1/p' "$STATE/err.tmp" | head -1)
  echo "${text:-cleaner failed or timed out}"
}

step() {
  flags=$1
  name=$2
  limit=$3
  shift 3
  "$PYTHON" "$CLEANER" $flags "$@" --state-root "$CLEANER_STATE" > "$STATE/$name.tmp" 2> "$STATE/err.tmp" &
  job=$!
  (sleep "$limit"; kill "$job" 2> /dev/null) &
  dog=$!
  wait "$job"
  code=$?
  pkill -P "$dog" 2> /dev/null
  kill "$dog" 2> /dev/null
  [ "$code" -eq 0 ] && mv "$STATE/$name.tmp" "$STATE/$name.json"
  return "$code"
}

if [ "$role" = start ]; then
  if ! mkdir "$LOCK" 2> /dev/null && lock_busy; then
    echo busy
    exit 0
  fi
  claim $$
  started=$(date +%s)
  status running 0 ""
  nohup sh "$0" "$mode" worker "$@" < /dev/null > /dev/null 2>&1 &
  waited=0
  while [ "$waited" -lt 50 ] && [ "$(cat "$LOCK/pid" 2> /dev/null)" = "$(record $$)" ]; do
    sleep 0.1
    waited=$((waited + 1))
  done
  echo started
  exit 0
fi

claim $$
started=$(date +%s)
[ "$mode" = archive ] && rm -f "$STATE/archive.json"
[ "$mode" = delete ] && rm -f "$STATE/delete.json"
failed=""
needs="--no-report"
[ "$mode" = clean ] && needs="--no-report --prune --include-t3-safe"
[ "$mode" = archive ] && needs="--no-report --archive"
[ "$mode" = delete ] && needs="--no-report --delete"
for flag in $needs; do
  "$PYTHON" "$CLEANER" --help 2> /dev/null | grep -q -- "$flag" || failed="cleaner out of date: missing $flag"
done
if [ -z "$failed" ]; then
  [ "$mode" = archive ] && { step "--archive" archive "$ARCHIVE_LIMIT" "$@" || failed=$(reason); }
  [ "$mode" = delete ] && { step "--delete" delete "$run_limit" "$@" || failed=$(reason); }
  if [ "$mode" = clean ] && step "--apply --prune --include-t3-safe --no-report" clean "$CLEAN_LIMIT"; then
    cp "$STATE/clean.json" "$STATE/last.tmp" && mv "$STATE/last.tmp" "$STATE/last.json" || failed="could not publish clean result"
  else
    [ "$mode" = clean ] && failed=$(reason)
    step "--dry-run --no-report" last "$SCAN_LIMIT" || failed=${failed:-$(reason)}
  fi
fi
finished=$(date +%s)
if [ -z "$failed" ]; then
  status done "$finished" ""
else
  status failed "$finished" "$failed"
fi
rm -f "$LOCK/pid"
rmdir "$LOCK"
