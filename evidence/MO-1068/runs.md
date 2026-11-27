# MO-1068 runs

Offline fixtures only; no live queue, journal or `coordq dispatch`.

## Ticket proof command

Red on `origin/main`:

```console
$ git show origin/main:coordinator/bin/coordq |
    grep -q 'prereview:' || echo "coordq has no prereview step"
coordq has no prereview step
```

Green on the head:

```console
$ grep -q 'prereview:' coordinator/bin/coordq && echo "exit 0"
exit 0
```

## Fixture cases

`prereview_gate_cases` in `coordinator/overnight/selftest.py`
(run from the gate-round-cap eval):

- Head touching `coordinator/bin/coordq`:
  - Queues one `prereview:` review item with the failure-path brief.
  - No gate until the thread is `completed`.
- Head touching only `coordinator/bin/journal.py`: no pre-review, gate runs.
- Dry run: nothing queued, nothing journaled.
- Gate runs and `prereview_skipped` is journaled once per head if:
  - The thread `failed`.
  - The thread is unreadable or stalled past 2 hours.
  - There is no different-vendor reviewer.
- Head whose gate already exists: never pre-reviewed.

On `origin/main` the case fails because the function is absent:
`AttributeError: ... has no attribute 'prereview_gate'`.
This command prints 0:
`git show origin/main:coordinator/bin/coordq | grep -c prereview_gate`.
On the head the case prints `GREEN prereview_gate_cases`.

## Selftest

`heavy python3 coordinator/overnight/selftest.py`: every case PASS, no FAIL line.
