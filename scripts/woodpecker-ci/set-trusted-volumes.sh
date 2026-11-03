#!/bin/sh
# MO-120: mark listed personal repos Trusted (Volumes) only — not network or
# privileged/security. Uses the Woodpecker admin API on the M1 (JWT minted
# from the admin user's hash in the live SQLite DB).
#
# Coordinates with MO-117: API-only (no agent restart, no Colima resize).
# Refuse to run while an SRW deploy workflow is running only as a soft
# warning — this script does not drain or restart agents.
#
# Usage (on M1, from ~/Code/woodpecker-ci/scripts or after install-to-m1):
#   ./set-trusted-volumes.sh
#   ./set-trusted-volumes.sh --dry-run
#   ./set-trusted-volumes.sh --undo
set -eu
PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export PATH

# shellcheck source=common.sh disable=SC1091
. "$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)/common.sh"

DRY_RUN=0
UNDO=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --undo) UNDO=1 ;;
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

# Explicit full_name allowlist (owner/name). Reject missing or ambiguous.
REPOS='
shyamsivakumar/strategy-replay-workbench
shyamsivakumar/mac-ops
shyamsivakumar/sams-llm-wiki
shyamsivakumar/cairn
shyamsivakumar/catalouge
shyamsivakumar/recoup
shyamsivakumar/CineJar
shyamsivakumar/scrapers
shyamsivakumar/scripture-scroll
shyamsivakumar/qabot
shyamsivakumar/fantasy-football-toolkit
shyamsivakumar/strata
'

API=http://127.0.0.1:8000

mint_token() {
  WP_HASH=$(query_db "SELECT hash FROM users WHERE admin = 1 ORDER BY id LIMIT 1;")
  WP_UID=$(query_db "SELECT id FROM users WHERE admin = 1 ORDER BY id LIMIT 1;")
  if [ -z "$WP_HASH" ] || [ -z "$WP_UID" ]; then
    echo "No admin user in Woodpecker DB" >&2
    exit 1
  fi
  export WP_HASH WP_UID
  /usr/bin/python3 - <<'PY'
import base64, hashlib, hmac, json, os
secret = os.environ["WP_HASH"].encode()
uid = os.environ["WP_UID"]
header = {"alg": "HS256", "typ": "JWT"}
payload = {"type": "user", "user-id": str(uid)}

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

h = b64url(json.dumps(header, separators=(",", ":")).encode())
p = b64url(json.dumps(payload, separators=(",", ":")).encode())
sig = hmac.new(secret, f"{h}.{p}".encode(), hashlib.sha256).digest()
print(f"{h}.{p}.{b64url(sig)}")
PY
}

api() {
  method=$1
  path=$2
  body=${3:-}
  if [ -n "$body" ]; then
    /usr/bin/curl -sS -X "$method" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "$API$path"
  else
    /usr/bin/curl -sS -X "$method" \
      -H "Authorization: Bearer $TOKEN" \
      "$API$path"
  fi
}

# Escape a single SQL string literal (full_name values are allowlisted).
sql_quote() {
  printf "%s" "$1" | sed "s/'/''/g"
}

volumes_wanted=true
if [ "$UNDO" -eq 1 ]; then
  volumes_wanted=false
  printf 'MO-120 undo: clearing Trusted volumes on listed repos.\n'
else
  printf 'MO-120: setting Trusted volumes=true (network/security unchanged).\n'
fi

if [ "$(srw_deploy_running)" != "0" ]; then
  printf 'Note: SRW deploy is running; continuing (API-only, no agent restart).\n' >&2
fi

TOKEN=$(mint_token)
me=$(api GET /api/user)
login=$(printf '%s' "$me" | /usr/bin/python3 -c 'import sys,json; print(json.load(sys.stdin)["login"])')
printf 'Authenticated as %s\n' "$login"

old_ifs=$IFS
IFS='
'
# shellcheck disable=SC2086
set -- $REPOS
IFS=$old_ifs
missing=0
for full in "$@"; do
  [ -n "$full" ] || continue
  q=$(sql_quote "$full")
  count=$(query_db "SELECT COUNT(*) FROM repos WHERE full_name = '$q';")
  if [ "$count" != "1" ]; then
    printf 'REJECT %s (exact full_name matches=%s; need exactly 1)\n' "$full" "$count" >&2
    missing=1
    continue
  fi
  row=$(query_db "SELECT id || '|' || full_name || '|' || trusted FROM repos WHERE full_name = '$q';")
  id=${row%%|*}
  rest=${row#*|}
  got=${rest%%|*}
  trusted_json=${rest#*|}
  if [ "$got" != "$full" ]; then
    printf 'REJECT %s (DB returned %s)\n' "$full" "$got" >&2
    missing=1
    continue
  fi
  current=$(printf '%s' "$trusted_json" | /usr/bin/python3 -c 'import sys,json; t=json.load(sys.stdin); print("volumes=%s network=%s security=%s" % (t.get("volumes"), t.get("network"), t.get("security")))')
  body=$(VOLUMES="$volumes_wanted" /usr/bin/python3 -c 'import json,os; print(json.dumps({"trusted":{"volumes": os.environ["VOLUMES"]=="true"}}))')
  printf 'REPO %s id=%s before[%s]\n' "$full" "$id" "$current"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  dry-run: would PATCH trusted.volumes=%s\n' "$volumes_wanted"
    printf '  undo: ./set-trusted-volumes.sh --undo  # or PATCH {"trusted":{"volumes":false}} for this repo\n'
    continue
  fi
  out=$(api PATCH "/api/repos/$id" "$body")
  after=$(printf '%s' "$out" | /usr/bin/python3 -c 'import sys,json; t=json.load(sys.stdin).get("trusted",{}); print("%s %s %s" % (t.get("volumes"), t.get("network"), t.get("security")))')
  printf '  after[volumes/network/security=%s]\n' "$after"
  vol=$(printf '%s' "$after" | awk '{print $1}')
  net=$(printf '%s' "$after" | awk '{print $2}')
  sec=$(printf '%s' "$after" | awk '{print $3}')
  if [ "$net" = "True" ] || [ "$net" = "true" ]; then
    echo "Refusing to leave network trusted on $full" >&2
    exit 1
  fi
  if [ "$sec" = "True" ] || [ "$sec" = "true" ]; then
    echo "Refusing to leave security/privileged trusted on $full" >&2
    exit 1
  fi
  if [ "$UNDO" -eq 1 ]; then
    if [ "$vol" != "False" ] && [ "$vol" != "false" ]; then
      echo "Undo failed for $full (volumes still $vol)" >&2
      exit 1
    fi
    printf '  undo applied; re-enable: PATCH /api/repos/%s {"trusted":{"volumes":true}}\n' "$id"
  else
    if [ "$vol" != "True" ] && [ "$vol" != "true" ]; then
      echo "Apply failed for $full (volumes=$vol)" >&2
      exit 1
    fi
    printf '  undo: PATCH /api/repos/%s {"trusted":{"volumes":false}}\n' "$id"
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "One or more allowlisted full_names were missing or ambiguous." >&2
  exit 1
fi

printf 'DB verification:\n'
query_db "SELECT full_name, trusted FROM repos WHERE full_name IN (
  'shyamsivakumar/strategy-replay-workbench','shyamsivakumar/mac-ops',
  'shyamsivakumar/sams-llm-wiki','shyamsivakumar/cairn','shyamsivakumar/catalouge',
  'shyamsivakumar/recoup','shyamsivakumar/CineJar','shyamsivakumar/scrapers',
  'shyamsivakumar/scripture-scroll','shyamsivakumar/qabot',
  'shyamsivakumar/fantasy-football-toolkit','shyamsivakumar/strata'
) ORDER BY full_name;"
