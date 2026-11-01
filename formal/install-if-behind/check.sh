#!/bin/sh
# Bounded TLC runs of the install_if_behind model.
# Raw TLC output stays under $TMPDIR. Parsed with /bin/sh -n, so this file stays POSIX.
set -u
ROOT="$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)"
JAVA="/opt/homebrew/opt/openjdk@17/bin/java"
JAR="/Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar"
DEST="${TMPDIR:-/tmp}/install-model-$$"
mkdir -p "$DEST"
cp "$ROOT"/formal/install-if-behind/InstallIfBehind.tla "$ROOT"/formal/install-if-behind/*.cfg "$DEST/"
cd "$DEST"

if [ ! -x "$JAVA" ] || [ ! -f "$JAR" ]; then
  echo "missing java or tla2tools.jar" >&2
  exit 2
fi

fail=0

run() {
  name="$1"
  expect="$2"
  needle="$3"
  echo "===== $name expect $expect ====="
  "$JAVA" -Djava.io.tmpdir="${TMPDIR:-/tmp}" -Xmx512m -jar "$JAR" \
    -workers 1 -metadir "$DEST/meta-$name" -config "$name.cfg" InstallIfBehind.tla \
    >"$DEST/$name.out" 2>&1
  code=$?
  echo "----- $name stats -----"
  grep -E "states generated|depth of the complete|Invariant .* is violated|No error has been found|^Error:" "$DEST/$name.out" || true
  if [ "$expect" = "pass" ]; then
    if [ "$code" -ne 0 ] || ! grep -q "No error has been found" "$DEST/$name.out"; then
      echo "FAIL $name expected a pass, exit $code" >&2
      tail -n 40 "$DEST/$name.out" >&2
      fail=1
    else
      echo "OK $name"
    fi
  elif ! grep -q "Invariant $needle is violated" "$DEST/$name.out"; then
    echo "FAIL $name expected Invariant $needle, exit $code" >&2
    tail -n 40 "$DEST/$name.out" >&2
    fail=1
  else
    echo "OK $name found Invariant $needle"
    sed -n '/^State 1:/,/^[0-9]* states generated/p' "$DEST/$name.out" | grep -E "^State|^/\\\\ (pc|active|receipt|note|origin)" 
  fi
}

run InstallSafety fail StableMeansVerified
run InstallFixed pass ""
run InstallNoPrev pass ""
run InstallLive pass ""

exit "$fail"
