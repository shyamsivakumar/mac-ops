#!/bin/sh
# Bounded TLC runs plus a dry-run replay of board_restart.tick.
# One heavy invocation runs this. Raw TLC output stays under $TMPDIR.
# Parsed with /bin/sh -n (dash on CI), so this file stays POSIX.
set -u
ROOT="$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)"
JAVA="/opt/homebrew/opt/openjdk@17/bin/java"
JAR="/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar"
DEST="${TMPDIR:-/tmp}/restart-model-$$"
mkdir -p "$DEST"
cp "$ROOT"/formal/restart/RestartLatch.tla "$ROOT"/formal/restart/*.cfg "$DEST/"
cd "$DEST"

if [ ! -x "$JAVA" ] || [ ! -f "$JAR" ]; then
  echo "missing java or tla2tools.jar" >&2
  exit 2
fi

fail=0

python3 "$ROOT/formal/restart/replay_latch.py" check || fail=1
python3 "$ROOT/formal/restart/replay_latch.py" mutate "$DEST/board_restart.py" || fail=1
python3 "$ROOT/formal/restart/replay_latch.py" module "$DEST/board_restart.py" mutant || fail=1

summarize() {
  name="$1"
  echo "----- $name stats -----"
  grep -E "states generated|depth of the complete|Invariant .* is violated|No error has been found|^Error:" "$DEST/$name.out" || true
}

run() {
  name="$1"
  expect="$2"
  cover="$3"
  needle="$4"
  meta="$DEST/meta-$name"
  echo "===== $name expect $expect ====="
  set +e
  if [ "$cover" = "yes" ]; then
    "$JAVA" -Djava.io.tmpdir="${TMPDIR:-/tmp}" -Xmx512m -jar "$JAR" \
      -coverage 1 -workers 1 -metadir "$meta" -config "$name.cfg" RestartLatch.tla \
      >"$DEST/$name.out" 2>&1
  else
    "$JAVA" -Djava.io.tmpdir="${TMPDIR:-/tmp}" -Xmx512m -jar "$JAR" \
      -workers 1 -metadir "$meta" -config "$name.cfg" RestartLatch.tla \
      >"$DEST/$name.out" 2>&1
  fi
  code=$?
  set -e
  summarize "$name"
  if [ "$expect" = "pass" ]; then
    if [ "$code" -ne 0 ] || ! grep -q "No error has been found" "$DEST/$name.out"; then
      echo "FAIL $name expected a pass, exit $code" >&2
      fail=1
    else
      echo "OK $name"
    fi
  else
    if ! grep -q "Invariant $needle is violated" "$DEST/$name.out"; then
      echo "FAIL $name expected Invariant $needle, exit $code" >&2
      tail -n 40 "$DEST/$name.out" >&2
      fail=1
    elif [ "$expect" = "gap" ]; then
      echo "KNOWN GAP $name: Invariant $needle is violated (crash before os.replace)"
    else
      echo "OK $name found Invariant $needle"
    fi
  fi
}

run RestartLatch pass yes ""
run RestartLive pass no ""
run RestartReach fail no NotYetRestarted
run RestartNoLatch fail no NoDoubleSuccess
run RestartCrash gap no NoDoubleSuccess
run RestartWipe fail no SavedLatch
run RestartBadInput fail no NoActionOnBadInput

if [ "$fail" -eq 0 ]; then
  echo "states and depth are in the stats lines above"
fi
exit "$fail"
