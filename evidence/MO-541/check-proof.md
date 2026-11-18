# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `d635774bed8ff1850810655255a608ead1dac7be`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-h291grm8 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-h291grm8/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Repair verification: choose() releases choosing in finally after success or failure. Duplicate choices remain blocked while the send is pending.

- passed: `node --check coordinator/mods/cockpit/main.js`
- passed: `git diff --check`
- not run: device, handset, live-service and live-board cases were waived by Shyam (2026-11-14).
- Comment diff review: no comments added or changed. Deslop review: no further cleanup in scope.

Single in-session Luna Max review: no critical or major findings.
Full suite: `python3 -m unittest discover -s tests` reports failures; final result recorded in PR body. Existing checks and tests were not changed.
