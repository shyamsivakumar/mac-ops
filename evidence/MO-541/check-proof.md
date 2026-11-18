# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `b6024d7c06b524773457c6d67cb2224a7ef0e1c9`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-6zn96mvr -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-6zn96mvr/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Scope repair: current origin/main merged. The merge-base diff contains asks.js, hub.js, main.js, ui.js and this receipt only. Shared flowlog.js is identical to origin/main; answer audit logging was removed to preserve its existing contract. MO-539 changes and unrelated receipts are outside this diff. Prior individual Sonnet findings remain unavailable.

Device, handset, live-service and live-board checks were not run and were waived by Shyam on 2026-11-14. Previous full-suite failures are historical; the documented repository check passed on this repair. No tests or checks were weakened.

Deslop: no further cleanup warranted. Comment review in diff mode: no new comments in this repair.
