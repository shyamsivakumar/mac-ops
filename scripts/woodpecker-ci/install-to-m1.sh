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
ci_slo_report.py
ci_slo_report.sh
ci_slo_daily.sh
set-repo-timeouts.sh
set-trusted-volumes.sh
setup-cache-dirs.sh
cache-cleanup.sh
disk-hygiene.sh
'
plists='
com.shyamsivakumar.woodpecker-reaper.plist
com.shyamsivakumar.woodpecker-backup-nightly.plist
com.shyamsivakumar.woodpecker-ci-slo-daily.plist
com.shyamsivakumar.woodpecker-cache-cleanup.plist
com.shyamsivakumar.woodpecker-disk-hygiene.plist
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

# Snippet is docs-only on the M1 (repos pull it from mac-ops), but keep a copy.
scp -o BatchMode=yes -q "$SRC/snippets/woodpecker-lint-step.yaml" \
  "$HOST:$DEST/scripts/woodpecker-lint-step.yaml" 2>/dev/null || true

printf 'Install OK. Smoke: ssh %s %s/scripts/drain-agent.sh --resume\n' \
  "$HOST" "$DEST"
printf 'Reaper/backup/ci-slo LaunchAgents point at %s/scripts/*.sh\n' "$DEST"
printf 'MO-118: bootstrap daily SLO + timeouts with:\n'
# Single-quoted remote body so a copied command expands $(id -u)/$DOMAIN on the M1,
# not in the caller's shell.
printf "  ssh %s 'DOMAIN=gui/\$(id -u); launchctl bootout \"\$DOMAIN\"/com.shyamsivakumar.woodpecker-ci-slo-daily 2>/dev/null; launchctl bootstrap \"\$DOMAIN\" %s/com.shyamsivakumar.woodpecker-ci-slo-daily.plist; launchctl enable \"\$DOMAIN\"/com.shyamsivakumar.woodpecker-ci-slo-daily'\n" \
  "$HOST" "$DEST"
printf '  ssh %s %s/scripts/set-repo-timeouts.sh\n' "$HOST" "$DEST"
printf 'MO-120: trusted volumes + cache dirs + daily cleanup:\n'
printf '  ssh %s %s/scripts/set-trusted-volumes.sh\n' "$HOST" "$DEST"
printf '  ssh %s %s/scripts/setup-cache-dirs.sh --colima\n' "$HOST" "$DEST"
printf '  ssh %s sudo %s/scripts/setup-cache-dirs.sh --host\n' "$HOST" "$DEST"
printf "  ssh %s 'DOMAIN=gui/\$(id -u); launchctl bootout \"\$DOMAIN\"/com.shyamsivakumar.woodpecker-cache-cleanup 2>/dev/null; launchctl bootstrap \"\$DOMAIN\" %s/com.shyamsivakumar.woodpecker-cache-cleanup.plist; launchctl enable \"\$DOMAIN\"/com.shyamsivakumar.woodpecker-cache-cleanup'\n" \
  "$HOST" "$DEST"
printf 'MO-122: daily disk hygiene (DerivedData cap + sim prune + alert <15%%):\n'
printf "  ssh %s 'DOMAIN=gui/\$(id -u); launchctl bootout \"\$DOMAIN\"/com.shyamsivakumar.woodpecker-disk-hygiene 2>/dev/null; launchctl bootstrap \"\$DOMAIN\" %s/com.shyamsivakumar.woodpecker-disk-hygiene.plist; launchctl enable \"\$DOMAIN\"/com.shyamsivakumar.woodpecker-disk-hygiene'\n" \
  "$HOST" "$DEST"
