#!/bin/sh
set -eu
PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH

HERE=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
STATE=${MAC_OPS_STATE:-$HOME/.local/state/mac-ops}/worktree-cleaner
umask 077
if [ -L "$STATE" ]; then
  printf '%s\n' 'unsafe worktree-cleaner state path' >&2
  exit 2
fi
mkdir -p "$STATE/logs"
if [ "${1-}" = "--dry-run" ]; then
  exec /usr/bin/python3 "$HERE/cleaner.py" --state-root "$STATE" "$@"
fi
exec /usr/bin/python3 "$HERE/cleaner.py" --state-root "$STATE" --apply "$@"
