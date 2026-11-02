#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
formal_dir="$repo_root/formal/governor"
task_tmp="${TMPDIR:?Set TMPDIR to the task scratch directory}"
mkdir -p "$task_tmp"
run_root="$(mktemp -d "$task_tmp/governor-formal.XXXXXX")"
model_copy="$run_root/Governor.tla"
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

source_model_sha="$(shasum -a 256 "$formal_dir/Governor.tla" | awk '{print $1}')"
cp "$formal_dir/Governor.tla" "$model_copy"
copied_model_sha="$(shasum -a 256 "$model_copy" | awk '{print $1}')"
if [[ "$source_model_sha" != "$copied_model_sha" ]]; then
  echo "The task-scratch TLA model copy does not match its source" >&2
  exit 1
fi
echo "TLA model SHA-256: $source_model_sha"

expected_sha="$(awk '{print $1}' "$tla_dir/tla2tools.sha256")"
actual_sha="$(shasum -a 256 "$jar" | awk '{print $1}')"
if [[ "$expected_sha" != "$actual_sha" ]]; then
  echo "The installed TLC jar does not match its checksum receipt" >&2
  exit 1
fi

mkdir -p "$run_root/sany/java"
status=0
set +e
"$java_bin" -Xmx512m -XX:+UseParallelGC "-Djava.io.tmpdir=$run_root/sany/java" \
  -cp "$jar" tla2sany.SANY "$model_copy" > "$run_root/sany.out" 2>&1
status=$?
set -e
if ((status != 0)) || rg -q 'Fatal errors|\*\*\*Parse Error\*\*\*|Semantic errors' "$run_root/sany.out"; then
  echo "SANY could not parse the governor model; read $run_root/sany.out" >&2
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
    -deadlock -coverage 1 -config "$config_path" \
    "$model_copy" > "$output_dir/tlc.out" 2>&1
  status=$?
  set -e
  if [[ "$expectation" == "pass" ]]; then
    if ((status != 0)) || rg -q '^Error:' "$output_dir/tlc.out" \
      || ! rg -Fq "Model checking completed" "$output_dir/tlc.out"; then
      echo "$name did not pass; read $output_dir/tlc.out" >&2
      exit 1
    fi
  elif ! rg -Fq "$marker" "$output_dir/tlc.out"; then
    echo "$name did not produce the expected counterexample; read $output_dir/tlc.out" >&2
    exit 1
  fi
  printf '%s: expected %s (TLC exit %s)\n' "$name" "$expectation" "$status"
}

run_tlc legacy-old-floor "$formal_dir/GovernorLegacy.chart.cfg" counterexample \
  "FloorAfterFreshNoncritical is violated"
run_tlc fixed-floor "$formal_dir/GovernorFixed.chart.cfg" pass
run_tlc legacy-no-start "$formal_dir/GovernorLegacyNoStart.cfg" counterexample \
  "Temporal property QueueStarts was violated"
run_tlc fixed-no-start "$formal_dir/GovernorFixedNoStart.cfg" pass
run_tlc safety "$formal_dir/GovernorSafety.cfg" pass
run_tlc conditional-liveness "$formal_dir/GovernorConditionalLiveness.cfg" pass
run_tlc strict-start-liveness "$formal_dir/GovernorStrictStart.cfg" counterexample \
  "Temporal property EligibleQueueStarts was violated"
run_tlc strict-no-critical-floor "$formal_dir/GovernorStrictNoCriticalFloor.cfg" counterexample \
  "NoncriticalTickFloor is violated"
run_tlc strict-no-critical-start "$formal_dir/GovernorStrictNoCriticalStart.cfg" counterexample \
  "Temporal property StrictNoCriticalQueueStarts was violated"
run_tlc strict-publication "$formal_dir/GovernorStrictPublish.cfg" counterexample \
  "CriticalTickComplete is violated"
run_tlc external-failure-probe "$formal_dir/GovernorFailureProbe.cfg" counterexample \
  "NoFailedStart is violated"
run_tlc coverage "$formal_dir/GovernorCoverage.cfg" pass

python3 - "$run_root/coverage/tlc.out" <<'PY'
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
actions = (
    "CaptureReading",
    "DecideTargets",
    "CensusFailure",
    "PublishCapacity",
    "PublishFailure",
    "RequestCriticalPause",
    "SignalAccepted",
    "SignalDenied",
    "RetrySignal",
    "PublishBoardLimit",
    "AdmitJob",
    "ExternalStartSuccess",
    "ExternalStartFailure",
    "ControllerRestart",
    "HostReboot",
    "ExpireCapacity",
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
print("Coverage: every modeled transition had a nonzero count with -coverage 1")
PY

echo "TLC scratch output: $run_root"
