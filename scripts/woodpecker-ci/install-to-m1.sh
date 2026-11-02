#!/bin/sh
# Copy the versioned woodpecker-ci scripts/plists/compose overlay onto the M1
# live stack at ~/Code/woodpecker-ci. Modes are forced executable for *.sh.
#
# Usage (from any machine with SSH Host m1):
#   ./scripts/woodpecker-ci/install-to-m1.sh
#   M1_HOST=shyams-m1 DEST=~/Code/woodpecker-ci ./scripts/woodpecker-ci/install-to-m1.sh
set -eu

SRC=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
HOST=${M1_HOST:-m1}
DEST=${DEST:-/Users/shyamsivakumar/Code/woodpecker-ci}

scripts='
common.sh
drain-agent.sh
reaper.sh
apply-two-lanes.sh
watchdog.sh
backup-nightly.sh
verify.sh
'
plists='
com.shyamsivakumar.woodpecker-reaper.plist
com.shyamsivakumar.woodpecker-backup-nightly.plist
'

printf 'Installing mac-ops woodpecker-ci overlay -> %s:%s\n' "$HOST" "$DEST"

ssh -o BatchMode=yes "$HOST" "mkdir -p '$DEST/scripts'"

for f in $scripts; do
  scp -o BatchMode=yes -q "$SRC/$f" "$HOST:$DEST/scripts/$f"
done
for f in $plists; do
  scp -o BatchMode=yes -q "$SRC/$f" "$HOST:$DEST/$f"
done
scp -o BatchMode=yes -q "$SRC/compose.yaml" "$HOST:$DEST/compose.yaml"

ssh -o BatchMode=yes "$HOST" "chmod 755 $DEST/scripts/*.sh && chmod 644 $DEST/*.plist $DEST/compose.yaml && ls -la $DEST/scripts $DEST/com.shyamsivakumar.woodpecker-*.plist"

printf 'Install OK. Smoke: ssh %s %s/scripts/drain-agent.sh --resume\n' \
  "$HOST" "$DEST"
printf 'Reaper/backup LaunchAgents still point at %s/scripts/*.sh\n' "$DEST"
