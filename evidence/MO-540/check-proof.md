# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `3ef549196b11c0c0c18c72512de9a7b73d745335`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-8kdzb0v5 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-8kdzb0v5/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Node syntax: passed (`node --check coordinator/mods/cockpit/main.js`).
Focused extracted-method probe: passed; captured Needs-you eligibility survives a refresh and false eligibility omits logging.
Device, handset and live-service testing: waived by Shyam (2026-11-14), not failed.
In-session review: reply/sendback and merge capture eligibility before awaits; logging remains on success. No critical or major findings. No comments added; diff cleanup review found no further changes.
Receipt records the checked source tree before the receipt commit; final commit is checked again and identified in the PR body.
