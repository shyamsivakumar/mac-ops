# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `7553c21ae248cd728a2e6908e75cf242cea2c185`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-gyjsotmt -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-gyjsotmt/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Additional checks: `node --check coordinator/mods/cockpit/main.js` passed. A `node --input-type=module` probe of the actual logAnswers method passed equal timestamps across ticks, duplicate suppression, newer same-key answers and older new-key answers.

Device, handset and live-service checks were not run: waived by Shyam in the brief.
Diff cleanup and comment review: no added comments or unrelated cleanup needed.
