#!/bin/bash
# The fake `ticket` and `gh` both append their argv to one log.
# usage: lock_replay.sh <checkout>
# Holds the shift lock the way a running cycle does, starts a second
# `overnight shift`, and counts the gh calls the second one makes.
CHECKOUT=$1
T=$(mktemp -d /private/tmp/lockreplay-XXXXXX)
mkdir -p "$T/root" "$T/bin" "$T/home/.local/state/mac-ops" "$T/home/Code/coordinator/queue"
echo '{"cap":6}' > "$T/home/Code/coordinator/queue/config.json"
cat > "$T/bin/gh" <<'GH'
#!/bin/bash
echo "$@" >> "$FAKE_GH_LOG"
echo '{"issues":[],"stale":false}'
GH
cp "$T/bin/gh" "$T/bin/ticket"
chmod +x "$T/bin/gh" "$T/bin/ticket"
export FAKE_GH_LOG="$T/gh-calls.log" OVERNIGHT_GH="$T/bin/gh" OVERNIGHT_TICKET="$T/bin/ticket" OVERNIGHT_SHIFT_LOCK="$T/shift.lock" \
  COORDINATOR_GH_USAGE_LOG="$T/usage.jsonl" HOME="$T/home" PATH="$T/bin:$PATH"
: > "$FAKE_GH_LOG"
python3 "$CHECKOUT/coordinator/overnight/overnight" policy --root "$T/root" 2>&1 | tail -1
python3 - "$OVERNIGHT_SHIFT_LOCK" <<'PY' &
import fcntl, sys, time
f = open(sys.argv[1], "a+"); fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); time.sleep(12)
PY
HOLDER=$!
sleep 1
timeout 60 python3 "$CHECKOUT/coordinator/overnight/overnight" shift --root "$T/root" 2>&1 | grep -v "^Retry\|^Builder\|^Verify\|^No item\|^The shift reads" | head -12
echo "second shift exit: ${PIPESTATUS[0]}; board reads (ticket list) and gh calls made by the second shift: $(wc -l < "$FAKE_GH_LOG" | tr -d ' ')"
kill $HOLDER 2>/dev/null; wait $HOLDER 2>/dev/null
