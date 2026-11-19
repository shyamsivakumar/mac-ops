#!/bin/bash
# Run the Harbor example task with the pi agent, and save the run logs.
#
# The model credential comes from the environment. The script reads it by name,
# never prints it, and never writes it to disk. Set the name and the endpoint
# with the HARBOR_* variables when a different model is wanted.
set -euo pipefail

ROOT=$(CDPATH= cd -P "$(dirname "$0")/../.." && pwd)
HARBOR_VERSION=0.26.0
MODEL=${HARBOR_MODEL:-MiniMax-M3.1-Flash}
BASE_URL=${HARBOR_BASE_URL:-https://api.minimax.io/anthropic}
API_FORMAT=${HARBOR_API_FORMAT:-anthropic_messages}
API_KEY_NAME=${HARBOR_API_KEY_NAME:-MINIMAX_API_KEY}
LOG_DIR=${HARBOR_LOG_DIR:-"$ROOT/evals/harbor/logs/pi-run"}
TASK=${HARBOR_TASK:-"$ROOT/evals/harbor/tasks/example"}

if ! command -v harbor >/dev/null 2>&1; then
  "$ROOT/evals/harbor/install.sh"
fi

if [ "$(python3 -c 'import os,sys;sys.stdout.write("yes" if os.environ.get(sys.argv[1]) else "")' "$API_KEY_NAME")" != "yes" ]; then
  echo "run-example.sh: $API_KEY_NAME is not set in the environment." >&2
  echo "run-example.sh: set it to the model API key, then run this script again." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

harbor run \
  -p "$TASK" \
  -a pi \
  -m "$MODEL" \
  --base-url "$BASE_URL" \
  --api-format "$API_FORMAT" \
  --api-key-name "$API_KEY_NAME" \
  -n 1 \
  -o "$LOG_DIR" \
  -y

echo "run-example.sh: logs are in $LOG_DIR"
