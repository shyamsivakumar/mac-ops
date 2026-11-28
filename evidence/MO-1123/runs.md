# MO-1123 runs

Offline fixtures only; no live queue, journal, lane or ticket.

## Ticket proof command

Red on `origin/main`:

```console
$ git show origin/main:coordinator/overnight/lane_driver.py |
    grep -q 'prereview' || echo "lane_driver has no prereview step"
lane_driver has no prereview step
```

Green: `grep -q 'prereview' coordinator/overnight/lane_driver.py` exits 0.

## Fixture cases

`prereview_findings_cases` in `coordinator/overnight/selftest.py`
(run from the gate-round-cap eval):

- Pre-review still running: nothing sent.
- `PREREVIEW: FINDINGS` reply: one fix message to the builder.
  - Key: `prereview-fix:<repo>#<n>:<head>`.
  - It has the findings text without the verdict line.
  - A second call for the same head sends nothing.
- `PREREVIEW: CLEAN`, no `PREREVIEW:` line, or empty reply: nothing sent.
  The last two journal `prereview_skipped` once.
- Unreadable thread: `prereview_skipped` journaled once, the gate path runs.
- No receipt for the head: nothing sent.
- Herdr-built repo with `Owner: t1j`: `prereview_findings` journaled,
  nothing sent, no card. Unowned: the existing build card.

On `origin/main` the case fails with `AttributeError`
(`prereview_findings` is absent). On the head it prints `GREEN`.

## Replacement ticket

#1123 replaces #1072. The #1072 proof command named `lane_driver` without
`.py`, so it failed with "No such file" in the gate's clean checkout. The #1123
proof command is `grep -q 'prereview' coordinator/overnight/lane_driver.py || ...`.
It exits 1 on `origin/main` and 0 on this branch, with `HOME=$(mktemp -d)`.
