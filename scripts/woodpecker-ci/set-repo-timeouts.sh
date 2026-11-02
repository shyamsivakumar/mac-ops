#!/bin/sh
# MO-118: server-wide default pipeline timeout 15m; per-repo overrides.
#
# - WOODPECKER_DEFAULT_PIPELINE_TIMEOUT=15 (compose; new repos)
# - WOODPECKER_MAX_PIPELINE_TIMEOUT stays ≥ max override (60)
# - Existing repos: UPDATE timeout=15, SRW deploy override=30
#
# Coordinates with MO-117: drains all agents before recreating the server
# so an SRW deploy is never cut mid-flight.
#
# Usage (on M1, from ~/Code/woodpecker-ci/scripts or after install-to-m1):
#   ./set-repo-timeouts.sh
#   ./set-repo-timeouts.sh --db-only          # skip compose recreate
#   DEFAULT_TIMEOUT=15 SRW_TIMEOUT=30 ./set-repo-timeouts.sh
set -eu
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH

# shellcheck source=common.sh disable=SC1091
. "$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)/common.sh"

DEFAULT_TIMEOUT=${DEFAULT_TIMEOUT:-15}
SRW_TIMEOUT=${SRW_TIMEOUT:-30}
SRW_MATCH=${SRW_MATCH:-%strategy-replay-workbench%}
DB_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --db-only) DB_ONLY=1 ;;
    -h | --help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

# Timeouts must be positive integers within the server max (60).
case "$DEFAULT_TIMEOUT" in *[!0-9]* | '' | 0)
  echo "DEFAULT_TIMEOUT must be a positive integer (got $DEFAULT_TIMEOUT)" >&2
  exit 1
  ;;
esac
case "$SRW_TIMEOUT" in *[!0-9]* | '' | 0)
  echo "SRW_TIMEOUT must be a positive integer (got $SRW_TIMEOUT)" >&2
  exit 1
  ;;
esac
if [ "$DEFAULT_TIMEOUT" -gt 60 ] || [ "$SRW_TIMEOUT" -gt 60 ]; then
  echo "timeouts must be ≤ WOODPECKER_MAX_PIPELINE_TIMEOUT=60" >&2
  exit 1
fi
# LIKE pattern: keep operator input from breaking out of the SQL string.
newline='
'
cr=$(printf '\r')
case "$SRW_MATCH" in
  *\'* | *\"* | *\`* | *\$* | *\\* | *"$newline"* | *"$cr"*)
    echo "SRW_MATCH contains unsafe characters: $SRW_MATCH" >&2
    exit 1
    ;;
esac

printf 'MO-118 timeouts: default=%sm SRW=%sm\n' "$DEFAULT_TIMEOUT" "$SRW_TIMEOUT"

apply_db() {
  write_db "UPDATE repos SET timeout = ${DEFAULT_TIMEOUT} WHERE full_name NOT LIKE '${SRW_MATCH}';"
  write_db "UPDATE repos SET timeout = ${SRW_TIMEOUT} WHERE full_name LIKE '${SRW_MATCH}';"
  printf 'Repo timeouts after update:\n'
  query_db "SELECT full_name, timeout FROM repos ORDER BY full_name;"
}

patch_compose() {
  compose_file="$ROOT/compose.yaml"
  if [ ! -f "$compose_file" ]; then
    echo "Missing $compose_file" >&2
    exit 1
  fi
  /usr/bin/python3 - "$compose_file" "$DEFAULT_TIMEOUT" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
default = sys.argv[2]
text = path.read_text()
if "WOODPECKER_DEFAULT_PIPELINE_TIMEOUT" in text:
    text = re.sub(
        r'(WOODPECKER_DEFAULT_PIPELINE_TIMEOUT:\s*")\d+(")',
        rf'\g<1>{default}\2',
        text,
        count=1,
    )
else:
    text = text.replace(
        'WOODPECKER_MAX_PIPELINE_TIMEOUT:',
        f'WOODPECKER_DEFAULT_PIPELINE_TIMEOUT: "{default}"\n'
        f'      WOODPECKER_MAX_PIPELINE_TIMEOUT:',
        1,
    )
# Keep max at least 60 so the SRW 30 override is legal in the UI/API.
if "WOODPECKER_MAX_PIPELINE_TIMEOUT" in text:
    text = re.sub(
        r'(WOODPECKER_MAX_PIPELINE_TIMEOUT:\s*")\d+(")',
        r'\g<1>60\2',
        text,
        count=1,
    )
path.write_text(text)
print(f"Patched {path} DEFAULT={default} MAX=60")
PY
}

recreate_server() {
  drain="$ROOT/scripts/drain-agent.sh"
  if [ ! -x "$drain" ]; then
    echo "Missing $drain; cannot safely recreate server" >&2
    exit 1
  fi
  printf 'Draining agents before server recreate (MO-117 lane guard)...\n'
  # drain-agent prints DRAIN_OPID=... before the idle wait; a later failure
  # still leaves an opid on stdout. Capture exit status separately and abort
  # recreate unless drain succeeded.
  drain_log=$(mktemp "${TMPDIR:-/tmp}/mo118-drain.XXXXXX")
  set +e
  "$drain" all 900 >"$drain_log" 2>&1
  drain_rc=$?
  set -e
  cat "$drain_log" >&2
  opid=$(awk -F= '/^DRAIN_OPID=/{print $2; exit}' "$drain_log")
  rm -f "$drain_log"
  if [ "$drain_rc" -ne 0 ]; then
    echo "Drain failed (rc=$drain_rc); not recreating server." >&2
    if [ -n "${opid:-}" ]; then
      echo "Drain op $opid may still be held; resume with: $drain --resume $opid" >&2
    fi
    exit "$drain_rc"
  fi
  if [ -z "${opid:-}" ]; then
    echo "Drain succeeded but did not print DRAIN_OPID" >&2
    exit 1
  fi
  printf 'Recreating server with new timeout env (opid=%s)...\n' "$opid"
  if ! compose up -d --force-recreate --no-deps server; then
    echo "compose recreate failed; leaving drain held (resume with --resume $opid)" >&2
    exit 1
  fi
  # Wait for health
  i=0
  until curl -fsS -o /dev/null http://127.0.0.1:8000/api/health; do
    i=$((i + 1))
    if [ "$i" -gt 60 ]; then
      echo "Server health check timed out; drain still held ($opid)" >&2
      exit 1
    fi
    sleep 2
  done
  "$drain" --resume "$opid"
  printf 'Server recreated; drain %s resumed.\n' "$opid"
}

apply_db

if [ "$DB_ONLY" -eq 1 ]; then
  printf 'DB-only mode: compose/server left unchanged.\n'
  exit 0
fi

patch_compose
recreate_server
printf 'MO-118 timeouts applied.\n'
