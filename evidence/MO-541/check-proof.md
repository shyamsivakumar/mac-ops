# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `28e6d523843f1c03a83fd5fa5c0e9418698b01e0`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-hgfwl_lu -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-hgfwl_lu/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

JavaScript syntax: passed (`node --check coordinator/mods/cockpit/main.js`).
Diff check: passed (`git diff --check`).
Device, handset, live-service and live-board checks: not run, waived by Shyam on 2026-11-14.
In-session review: numbered replies capture eligibility before delivery and record reply only after success; failures do not record reply. No comments added; no cleanup findings in the two-line code diff.
This receipt describes the checked working tree based on the commit above; the subsequent commit contains this code and receipt only. Selected checks are not the full suite.
