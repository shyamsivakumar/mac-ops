#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
formal_dir="$repo_root/formal/governor"
task_tmp="${TMPDIR:?Set TMPDIR to the task scratch directory}"
mkdir -p "$task_tmp"
run_root="$(mktemp -d "$task_tmp/board-floor-formal.XXXXXX")"
model_copy="$run_root/BoardFloor.tla"
wiki_root="${LLMWIKI_ROOT:-$HOME/Code/llmwiki}"
tla_dir="$wiki_root/runtime/tla"
jar="$tla_dir/tla2tools.jar"
java_bin="${JAVA_HOME:+$JAVA_HOME/bin/}java"

if [[ -z "${JAVA_HOME:-}" ]]; then
  for candidate in \
    /opt/homebrew/opt/openjdk@17/bin/java \
    /opt/homebrew/opt/openjdk/bin/java \
    /usr/bin/java; do
    if [[ -x "$candidate" ]] && "$candidate" -version >/dev/null 2>&1; then
      java_bin="$candidate"
      break
    fi
  done
fi
if [[ ! -x "$java_bin" ]] || ! "$java_bin" -version >/dev/null 2>&1; then
  echo "No working Java runtime found; set JAVA_HOME or use the installed OpenJDK 17+" >&2
  exit 1
fi
if [[ ! -f "$jar" ]]; then
  echo "Missing the pinned TLC jar under $tla_dir" >&2
  exit 1
fi

source_model_sha="$(shasum -a 256 "$formal_dir/BoardFloor.tla" | awk '{print $1}')"
cp "$formal_dir/BoardFloor.tla" "$model_copy"
copied_model_sha="$(shasum -a 256 "$model_copy" | awk '{print $1}')"
if [[ "$source_model_sha" != "$copied_model_sha" ]]; then
  echo "The task-scratch TLA model copy does not match its source" >&2
  exit 1
fi
echo "BoardFloor TLA model SHA-256: $source_model_sha"

expected_sha="$(awk '{print $1}' "$tla_dir/tla2tools.sha256")"
actual_sha="$(shasum -a 256 "$jar" | awk '{print $1}')"
if [[ "$expected_sha" != "$actual_sha" ]]; then
  echo "The installed TLC jar does not match its checksum receipt" >&2
  exit 1
fi
echo "TLC jar SHA-256: $actual_sha"

mkdir -p "$run_root/sany/java"
status=0
set +e
"$java_bin" -Xmx512m -XX:+UseParallelGC "-Djava.io.tmpdir=$run_root/sany/java" \
  -cp "$jar" tla2sany.SANY "$model_copy" > "$run_root/sany.out" 2>&1
status=$?
set -e
if ((status != 0)) || rg -q 'Fatal errors|\*\*\*Parse Error\*\*\*|Semantic errors' "$run_root/sany.out"; then
  echo "SANY could not parse the board-floor model; read $run_root/sany.out" >&2
  exit 1
fi
echo "SANY parse: pass"

run_tlc() {
  local name="$1"
  local config_path="$2"
  local expectation="$3"
  local marker="${4:-}"
  local output_dir="$run_root/$name"
  mkdir -p "$output_dir/meta" "$output_dir/java"
  local status=0
  set +e
  "$java_bin" -Xmx512m -XX:+UseParallelGC "-Djava.io.tmpdir=$output_dir/java" \
    -cp "$jar" tlc2.TLC -workers 1 -metadir "$output_dir/meta" \
    -deadlock -coverage 1 -config "$config_path" "$model_copy" \
    > "$output_dir/tlc.out" 2>&1
  status=$?
  set -e
  if [[ "$expectation" == "pass" ]]; then
    if ((status != 0)) || rg -q '^Error:' "$output_dir/tlc.out" \
      || ! rg -Fq "Model checking completed" "$output_dir/tlc.out"; then
      echo "$name did not pass; read $output_dir/tlc.out" >&2
      exit 1
    fi
  elif ((status == 0)) || ! rg -Fq "$marker" "$output_dir/tlc.out"; then
    echo "$name did not produce the expected counterexample; read $output_dir/tlc.out" >&2
    exit 1
  fi
  printf '%s: expected %s (TLC exit %s)\n' "$name" "$expectation" "$status"
}

run_tlc fixed-safety "$formal_dir/BoardFloorSafety.cfg" pass
run_tlc fixed-liveness "$formal_dir/BoardFloorLiveness.cfg" pass
run_tlc ceiling-seven "$formal_dir/BoardFloorCeiling7.cfg" pass
run_tlc healthy-window-growth "$formal_dir/BoardFloorGrowth.cfg" pass
run_tlc legacy-floor "$formal_dir/BoardFloorLegacyFloor.cfg" counterexample \
  "Invariant FreshFloorDecision is violated"
run_tlc legacy-no-start "$formal_dir/BoardFloorLegacyNoStart.cfg" counterexample \
  "Temporal property QueueStarts was violated"
run_tlc strict-recheck "$formal_dir/BoardFloorStrictRecheck.cfg" counterexample \
  "Temporal property BoardFloorLiveness was violated"
run_tlc strict-write "$formal_dir/BoardFloorStrictWrite.cfg" counterexample \
  "Temporal property BoardFloorLiveness was violated"
run_tlc strict-start "$formal_dir/BoardFloorStrictStart.cfg" counterexample \
  "Temporal property QueueStarts was violated"
run_tlc strict-critical-write "$formal_dir/BoardFloorStrictCriticalWrite.cfg" counterexample \
  "Invariant CriticalTickZero is violated"
run_tlc coverage "$formal_dir/BoardFloorCoverage.cfg" pass

python3 - "$run_root/coverage/tlc.out" <<'PY'
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
actions = (
    "CaptureReading",
    "DecideTarget",
    "RecheckAccepted",
    "RecheckRejected",
    "RecheckNotNeeded",
    "WriteSuccess",
    "WriteFailure",
    "NoWriteNeeded",
    "StartQueuedJob",
    "StartFailure",
)
missing = []
for action in actions:
    counts = [
        int(match.group(1))
        for line in text.splitlines()
        if action in line
        for match in [re.search(r"(?:^|[:=]\s*|\s)([0-9]+)\s*$", line)]
        if match
    ]
    if not counts or max(counts) == 0:
        missing.append(action)
if missing:
    raise SystemExit("No nonzero TLC coverage count for: " + ", ".join(missing))
print("Coverage: every modeled board-floor transition had a nonzero count with -coverage 1")
PY

repo_trace="$(find "$formal_dir" -maxdepth 1 -name 'BoardFloor_TTrace_*' -print -quit)"
if [[ -n "$repo_trace" ]]; then
  echo "TLC trace unexpectedly spilled into the worktree: $repo_trace" >&2
  exit 1
fi

echo "TLC scratch output: $run_root"
