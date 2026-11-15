# Ticket 358 acceptance receipt

Refs #358. PR: https://github.com/shyamsivakumar/mac-ops/pull/361

## Synthetic missing-module rollback

Ran a synthetic install using a temporary home and a checkout assembled from
the derived installer manifest, with `tick_health.py` omitted. The installed
`coordq` initially contained sentinel bytes with mode 0700. The real installer
transaction and `/opt/homebrew/bin/python3` smoke subprocesses ran. The shared
fixture supplied synthetic queue configuration, T3 responses, and a launchctl
stub. Manual-monitor inspection and job reload were mocked. No live install or
service operation ran. The real-HOME environment guard was not changed.

Verified every backup-manifest entry after the expected exception: pre-existing
files matched saved bytes and modes; newly created targets were absent. The
original coordq sentinel and mode were restored, and job reload was not called.

```text
Synthetic missing-module install: FAIL as required
Error: ModuleNotFoundError: No module named 'tick_health'
Rollback: PASS; verified all 101 transaction entries, original coordq bytes/mode restored
Job reload: not called; no live install or service calls
```

The FAIL above is the required rejection of an incomplete checkout. The proof
itself passed. It does not establish real-HOME or live-service health.

## Explicit live acceptance waiver

Authorization: coordinator instruction in the builder thread following the gate
FAIL on head a94e2b96ae1321fe8e342d90e82cbbb3108f7333:

> Device, handset and live-service testing is waived (Shyam 2026-11-14: "no testing is needed lets just finish backlog building everything"). Do not run device or live cases; state in the receipt that they were waived, not failed. Findings that only ask for device or live results are resolved by that statement.

Accordingly, successful real-HOME installation, live `healthy` status, and their
live smoke transcripts are **WAIVED**, not failed. They were not executed or
claimed. This receipt supplies the explicit authorization requested by the gate;
the waiver is repeated in the PR body so the gate can read it without local
coordinator files or private thread context.

The repository check runs separately on the final commit. Its exact head and
PASS line are recorded in the PR body. No runtime implementation, smoke
requirement, or existing assertion was changed for this gate finding.
