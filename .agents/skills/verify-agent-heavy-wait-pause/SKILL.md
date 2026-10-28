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

## Command

From the mac-ops repo root:

```bash
/usr/bin/python3 -m unittest tests.test_agent_heavy_wait_pause -v
/usr/bin/python3 -m compileall -q agent_heavy_wait_pause.py board_governor.py board_resources.py
```

A unittest pass is the bounded check. Live load drop with queued
agents is scorecard evidence, not a merge gate.

## Failure triage

- Pause with a foreground tool running: modeling error in `_agent_busy` allowlist.
- Heavy supervisor stopped: pause set included supervisor subtree; fix exclusions.
- Agent left paused after queue drain: resume path or state file;
  inspect `agent-heavy-wait-pause.json` and the controller log
  `agent_heavy_wait_pause` field.
