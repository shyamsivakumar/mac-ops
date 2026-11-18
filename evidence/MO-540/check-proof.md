# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `6cc2943f54466581e0e4d2dac18cc7cebeba5cfc`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-kf8x3hyu -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-kf8x3hyu/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Node syntax: passed (`node --check coordinator/mods/cockpit/main.js`).
Extracted tellEach bulk refresh and rejected-send probe: passed (`node --input-type=module`, in-session).
In-session review: eligibility is captured for all fresh cards before attempt and before any await; rejected delivery skips noteAct. No critical or major findings.
Device, handset and live-service testing: waived by Shyam, not failed.

Scope: checked the modified main.js source before commit.

PASS: `node --check coordinator/mods/cockpit/main.js`.
PASS: `git diff --check`.
PASS: inline Node mergeOne probe with mocked queue: validation reached, successful queue records eligible act, refusal records no act, missing seen card is ineligible.
Device, handset and live-service testing: not run, waived by Shyam.
In-session reviewer round: inspected mergeOne and tellEach scopes and act recording; no remaining critical or major findings. No comments added; no-comments diff review clear. Deslop skipped cleanup because checkout contained unrelated work at start.
