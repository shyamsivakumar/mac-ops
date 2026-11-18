# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `af5e46fb6558d2fc0eb797cdd06a13543e84373d`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-rvkwr_lr -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-rvkwr_lr/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

JavaScript syntax: passed, `node --check` on asks.js, hub.js, main.js, ui.js and flowlog.js under coordinator/mods/cockpit.

Diff whitespace: passed, `git diff --check`.

In-session review: main diff against origin/main contains only option selection and answer logging. Snooze, merge, reply and coordinator-wide action logging removed. Flow-log event support is required by option answers. No added code comments.

Device, handset, live-service and live-board cases: waived by Shyam per brief; not run.

Prior Sonnet findings: unavailable; individual resolution cannot be verified. Unsupported resolution claim removed.

Full Python suite: failed, `python3 -m unittest discover -s tests`: 386 tests, 7 failures. No tests modified.
