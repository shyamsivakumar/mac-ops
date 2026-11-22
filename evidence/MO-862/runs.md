# MO-862 runs

## Proof command on origin/main (red)
```
AssertionError: /private/tmp/claude-501/-Users-shyamsivakumar-Code/c283b00e-e8c8-422f-9aa1-eb7c969bb5ce/scratchpad/m862/main/coordinator/overnight/caps.log
exit: 1 (AssertionError)
```

## Proof command on the head (green)
```
exit: 0
```

## Fake 25-minute thread, temp HOME, interrupt mocked
```
- cap mis-sized 2026-11-22T17:13Z | t3 | ticket:fake/repo#1:a1 | fake-run | 25.0 min
- cap hit 2026-11-22T17:13Z | t3 | ticket:fake/repo#1:a1 | fake-run | 25.0 min
interrupt calls (mocked, nothing real): [('t3mcp', 't3_thread_interrupt', {'threadId': 'fake-thread', 'runId': 'fake-run'})]
STATE: /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmprppbk4ws/Code/coordinator/loop/.turn_cap.json
FILE: /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmprppbk4ws/Code/coordinator/loop/.turn_cap.json
FILE: /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmprppbk4ws/Code/coordinator/loop/caps.log
FILE: /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmprppbk4ws/Code/coordinator/loop/ticks.log
caps.log:
- cap mis-sized 2026-11-22T17:13Z | t3 | ticket:fake/repo#1:a1 | fake-run | 25.0 min
- cap hit 2026-11-22T17:13Z | t3 | ticket:fake/repo#1:a1 | fake-run | 25.0 min

```

## Selftest case turncap, head selftest against origin/main turn_cap.py (red)
```
    raise AssertionError(f"expected {expected!r}, got {actual!r}")
AssertionError: expected ['- cap mis-sized 2026-11-15T00:40Z | t3 | ticket:fixture/repo#2:a1 | paused-run | 10.0 min\n', '- cap mis-sized 2026-11-15T00:40Z | t3 | ticket:fixture/repo#2:a1 | paused-run | 10.0 min\n', '- cap hit 2026-11-15T00:50Z | t3 | ticket:fixture/repo#2:a1 | paused-run | 20.0 min
```

## Selftest case turncap on the head (green)
```
turncap PASS
```

## Installer status with temp HOME and a stale loop copy
```
  "retired_leftovers": [
    "/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.1cXU4kORaF/Code/coordinator/loop/turn_cap.py"
  ]
}
```
(The stale copy is only reported; the file is still in place after the status call.)

## turncap.log root cause: four theories

Evidence gathered 22 Nov. Job pid 68851 started 16 Nov 00:25 (`ps -o lstart`); plist and `~/.local/bin/turn_cap.py` mtime 16 Nov 00:25.

1. Launchd never created the file or the job writes nothing. REFUTED. `launchctl print gui/501/dev.coordinator.turncap` shows state running, stdout and stderr paths set to turncap.log, `runs = 1`. `lsof -p 68851` shows fd 1 and fd 2 open on `.../Logs/coordinator/turncap.log`, 190787 bytes, inode 510712570. The script prints `t3: N running thread(s)` every 60 seconds and the plist sets PYTHONUNBUFFERED=1, so it does write.
2. The path in the plist is wrong. REFUTED. The path launchd prints equals the path lsof shows, and the directory is the same one that holds tick.log and lanes.log.
3. A sweep unlinked the file while the job held it open. CONFIRMED. `ls` of the directory has no turncap.log, yet the process holds an open fd to a 190 KB file in that directory: it is unlinked, and the process keeps appending to a file nobody can see. `~/Library/Logs/mole/operations.log` has `REMOVED /Users/shyamsivakumar/Library/Logs/coordinator` from `mo clean` on 13 Nov, 15 Nov, 19 Nov (14.9MB), 20 Nov (12.0MB) and 21 Nov 07:52 (10.8MB). The job started 16 Nov, so the 19, 20 and 21 Nov runs removed the log it had open. `tmp-sweep` has no Logs path (grep).
4. The Mole whitelist protects the directory but the file is gone anyway. PARTLY TRUE, already fixed outside this repo. `~/.config/mole/whitelist` (mtime 21 Nov 11:27) now lists `/Users/shyamsivakumar/Library/Logs/coordinator`, and the 22 Nov 09:30 run logged `SKIPPED ... (whitelist)`. The whitelist did not exist when the job started, so the file stayed unlinked and the running process never reopened it.

Cause: Mole `mo clean` deleted the log directory before the whitelist entry existed. The whitelist entry is in place, so no cleaner change is needed in this repo. The file returns when launchd reopens its output, which happens only when the job restarts (manual step after merge). The code fix is the per-hit and per-warning stdout line, so a visible log also shows each interrupt.
