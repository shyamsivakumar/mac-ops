#!/bin/sh
# Bounded TLC runs of the Woodpecker runner lifecycle model.
# One heavy invocation runs this. Raw TLC output stays under $TMPDIR.
# Parsed with /bin/sh -n (dash on CI), so this file stays POSIX.
set -u
ROOT="$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)"
JAVA="/opt/homebrew/opt/openjdk@17/bin/java"
JAR="${MAC_OPS_TLA_JAR:-/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar}"
DEST="${TMPDIR:-/tmp}/woodpecker-runner-model-$$"
mkdir -p "$DEST"
cp "$ROOT"/formal/woodpecker-runner/RunnerLifecycle.tla "$ROOT"/formal/woodpecker-runner/*.cfg "$DEST/"
cd "$DEST"

if [ ! -x "$JAVA" ] || [ ! -f "$JAR" ]; then
  echo "missing java or tla2tools.jar" >&2
  exit 2
fi

fail=0

summarize() {
  name="$1"
  echo "----- $name stats -----"
  grep -E "states generated|depth of the complete|Invariant .* is violated|Temporal propert.* violated|No error has been found|^Error:" "$DEST/$name.out" || true
}

run() {
  name="$1"
  expect="$2"
  kind="$3"
  needle="$4"
  meta="$DEST/meta-$name"
  echo "===== $name expect $expect $needle ====="
  set +e
  "$JAVA" -Djava.io.tmpdir="${TMPDIR:-/tmp}" -Xmx512m -jar "$JAR" \
    -workers 1 -metadir "$meta" -config "$name.cfg" RunnerLifecycle.tla \
    >"$DEST/$name.out" 2>&1
  code=$?
  set -e
  summarize "$name"
  if [ "$expect" = "pass" ]; then
    if [ "$code" -ne 0 ] || ! grep -q "No error has been found" "$DEST/$name.out"; then
      echo "FAIL $name expected a pass, exit $code" >&2
      tail -n 40 "$DEST/$name.out" >&2
      fail=1
    else
      echo "OK $name"
    fi
  else
    missing=""
    for n in $needle; do
      if [ "$kind" = "inv" ]; then
        pattern="Invariant $n is violated"
      else
        pattern="Temporal propert.*$n.*violated"
      fi
      grep -q "$pattern" "$DEST/$name.out" || missing="$missing $n"
    done
    if [ "$code" -eq 0 ] || ! grep -q "counter-example\|behavior up to this point" "$DEST/$name.out"; then
      missing="$missing (no counterexample, exit $code)"
    fi
    if [ -n "$missing" ]; then
      echo "FAIL $name expected $needle violated, missing:$missing, exit $code" >&2
      tail -n 40 "$DEST/$name.out" >&2
      fail=1
    else
      echo "KNOWN BUG $name: $needle violated"
    fi
  fi
}

run RunnerNoPartition pass none ""
run RunnerDoubleRun fail inv NoDoubleRun
run RunnerInstallGap fail inv RunnerAlwaysUp
run RunnerStaleDrop fail prop JobsReported
run RunnerNoRollback fail prop "RunnerComesBack FailedInstallRollsBack"

if [ "$fail" -eq 0 ]; then
  echo "all expectations met; raw output in $DEST"
fi
exit "$fail"
