#!/bin/sh
# MO-120: create /var/lib/woodpecker-cache/<repo>/<kind> on agent hosts.
#
# Targets:
#   --colima   inside the Colima woodpecker VM (Docker agents ci-linux/ci-deploy)
#   --host     macOS host for the native agent (needs sudo for /var/lib)
#   --all      both (default)
#
# Owner/mode: root:root 0750 on Colima; root:admin 0770 on macOS so the
# LaunchAgent user (admin group) and CI can write, others cannot read.
# Never stores secrets — dependency caches only.
#
# Does not restart agents (MO-117: never restart during an SRW deploy).
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export PATH

ROOT_CACHE=${ROOT_CACHE:-/var/lib/woodpecker-cache}
CONTEXT=${CONTEXT:-colima-woodpecker}
DOCKER=${DOCKER:-/opt/homebrew/bin/docker}

REPOS='strategy-replay-workbench mac-ops sams-llm-wiki cairn catalouge recoup CineJar scrapers scripture-scroll qabot fantasy-football-toolkit strata'
KINDS='npm node_modules pip spm DerivedData tools'

DO_COLIMA=0
DO_HOST=0
case "${1:---all}" in
  --colima) DO_COLIMA=1 ;;
  --host) DO_HOST=1 ;;
  --all)
    DO_COLIMA=1
    DO_HOST=1
    ;;
  -h | --help)
    sed -n '1,25p' "$0"
    exit 0
    ;;
  *)
    echo "Unknown arg: $1" >&2
    exit 2
    ;;
esac

make_tree() {
  root=$1
  mkdir -p "$root"
  for repo in $REPOS; do
    for kind in $KINDS; do
      mkdir -p "$root/$repo/$kind"
    done
  done
}

setup_colima() {
  printf 'MO-120: creating %s inside Colima profile woodpecker...\n' "$ROOT_CACHE"
  "$DOCKER" --context "$CONTEXT" run --rm --privileged \
    -e ROOT_CACHE="$ROOT_CACHE" \
    -v /var/lib:/var/lib \
    alpine:3.22 \
    sh -c "
      set -eu
      ROOT=\"\$ROOT_CACHE\"
      mkdir -p \"\$ROOT\"
      for repo in $REPOS; do
        for kind in $KINDS; do
          mkdir -p \"\$ROOT/\$repo/\$kind\"
        done
      done
      chown -R root:root \"\$ROOT\"
      find \"\$ROOT\" -type d -exec chmod 0750 {} +
      find \"\$ROOT\" -type f -exec chmod 0640 {} +
      ls -la \"\$ROOT\"
    "
  printf 'Colima cache root ready at %s (VM-local).\n' "$ROOT_CACHE"
}

setup_host() {
  printf 'MO-120: creating %s on macOS host (sudo)...\n' "$ROOT_CACHE"
  if [ "$(id -u)" -eq 0 ]; then
    make_tree "$ROOT_CACHE"
    chown -R root:admin "$ROOT_CACHE"
    find "$ROOT_CACHE" -type d -exec chmod 0770 {} +
    find "$ROOT_CACHE" -type f -exec chmod 0660 {} +
  elif sudo -n true 2>/dev/null; then
    sudo mkdir -p "$ROOT_CACHE"
    # shellcheck disable=SC2086
    for repo in $REPOS; do
      for kind in $KINDS; do
        sudo mkdir -p "$ROOT_CACHE/$repo/$kind"
      done
    done
    sudo chown -R root:admin "$ROOT_CACHE"
    sudo find "$ROOT_CACHE" -type d -exec chmod 0770 {} +
    sudo find "$ROOT_CACHE" -type f -exec chmod 0660 {} + 2>/dev/null || true
  else
    echo "Host path $ROOT_CACHE needs sudo once. Re-run:" >&2
    echo "  sudo $0 --host" >&2
    echo "Until then native-agent caches will fail to mount." >&2
    exit 1
  fi
  ls -la "$ROOT_CACHE"
  printf 'macOS host cache root ready at %s.\n' "$ROOT_CACHE"
}

if [ "$DO_COLIMA" -eq 1 ]; then
  setup_colima
fi
if [ "$DO_HOST" -eq 1 ]; then
  setup_host
fi
printf 'MO-120 cache dirs done.\n'
