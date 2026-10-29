---
name: verify-agent-heavy-wait-pause
description: Verify controller pauses idle board agents waiting in the heavy queue after changing agent_heavy_wait_pause.py, board_governor controller ticks, or board agent census collection.
---

# Verify agent heavy-queue wait pauses

Run after changing idle-agent pause logic, controller wiring, or pane process census.

## Property

A task only waiting for heavy admission gets `SIGSTOP` on agent-side
processes; the heavy supervisor keeps running. Resume happens on
admission, cancel, busy foreground, census loss, restart, or tick error.

## Covered code and sync

- `agent_heavy_wait_pause.py` (`tick`, `resume_all`, `_pause_targets`)
- `board_governor.py` (`controller_tick`, `run_controller`, `_agent_heavy_wait_pause_tick`)
- `board_resources.py` (`board_agent_rss_census`, `_collect_agents` process_info)
- Sync commit: update after confirming verification matches code at the new commit.
- The `formal/agent-pause/ResumeRetry.tla` model covers a single tracked
  identity after an incomplete census. It checks that a failed resume stays
  tracked and that a successful resume occurs at most once in the model.
  Under weak fairness for a census tick and a successful retry, it also
  checks eventual resume. The model abstracts a completed tick and its state
  write as one action. `PersistFailedCensusResume` and
  `PersistSuccessfulCensusResume` abstract `tick` at
  `agent_heavy_wait_pause.py:365-393` and its caller's state write at
  `board_governor.py:621-645`. `Retry` abstracts
  `agent_heavy_wait_pause.py:358-363`. It does not prove controller startup
  recovery, crash safety between signal and persistence, eligibility,
  freshness, process identity, multiple identities, or repeated stop cycles.
- The model describes `agent_heavy_wait_pause.py` at `6a42e04` plus the
  change that preserves the `resume_all` result on census loss. Advance the
  sync commit only after comparing those paths and rerunning both configs.

## Command

From the mac-ops repo root:

```bash
/usr/bin/python3 -m unittest tests.test_agent_heavy_wait_pause -v
/usr/bin/python3 -m compileall -q agent_heavy_wait_pause.py board_governor.py board_resources.py
```

Run the model with the pinned wiki jar. Copy the files to a task-owned
temporary directory first because TLC writes counterexample traces beside the
model:

```bash
mkdir -p "$TMPDIR/resume-model"
cp formal/agent-pause/ResumeRetry* "$TMPDIR/resume-model/"
cd "$TMPDIR/resume-model"
heavy /opt/homebrew/opt/openjdk@17/bin/java -Djava.io.tmpdir="$TMPDIR" -Xmx512m -jar /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar -workers 1 -metadir "$TMPDIR/tlc-resume" -config ResumeRetry.cfg ResumeRetry.tla
heavy /opt/homebrew/opt/openjdk@17/bin/java -Djava.io.tmpdir="$TMPDIR" -Xmx512m -jar /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar -workers 1 -metadir "$TMPDIR/tlc-resume-bug" -config ResumeRetryBug.cfg ResumeRetry.tla
```

The first command should pass. The second reproduces the earlier lost-failure
behavior and should violate `Tracked`. Interpret both as model checks, not
as executions of the Python controller. Replay failures through `tick` with
controlled signal results before calling them code bugs.

A unittest pass is the bounded check. Live load drop with queued
agents is scorecard evidence, not a merge gate.

## Failure triage

- Pause with a foreground tool running: modeling error in `_agent_busy` allowlist.
- Heavy supervisor stopped: pause set included supervisor subtree; fix exclusions.
- Agent left paused after queue drain: resume path or state file;
  inspect `agent-heavy-wait-pause.json` and the controller log
  `agent_heavy_wait_pause` field.
