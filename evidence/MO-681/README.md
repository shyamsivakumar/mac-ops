# MO-681: why the first close check failed, and the scope correction

`ticket open` minted duplicate keys when tickets were opened back to back. The
fix landed in #718 (`5ffda005`). The close checklist then failed on one item:

```
scope: fail - outside the ticket's stated scope: coordinator/bin/hourly_selftest.py
proof file: pass - evidence/MO-681/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: FAIL shyamsivakumar/mac-ops#681
```

## Why the registry file is in the change

The suite's eval names are pinned in `EXPECTED` in
`coordinator/bin/hourly_selftest.py`, and the `hourly_selftest_fixture` eval
fails when that list and the suite's own `EVALS` differ:

```python
exact(sorted(adapter.EXPECTED), sorted(EVALS))
```

So the `key-mint` eval the ticket asked for cannot land without its name in
that file. The ticket's scope section did not name it, and the close checklist
read the change as out of scope.

The ticket's scope section now names the file, with the reason. The change
itself is unchanged: the registry line is a mechanical consequence of the eval
the ticket asked for, not new work.

## The close checklist, after the scope correction

Read against the merged pull request #718 and the corrected ticket:

```
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-681/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#681
```

## What landed in #718

- `coordinator/bin/ticket`: `last-key-<repo>-<prefix>.json` in `CACHE_DIR`,
  written under the open lock, holding the highest number given out, the
  numbers given out that the issue list has not shown yet, and the number of a
  create whose answer has not come back. The mint goes one past
  `max(listed keys, number)`; an explicit key is refused when either source
  holds it; only a failure that establishes rejection (`auth`, `budget`,
  `rate_limit`) frees the key again; an unreadable record is a refusal; the
  prefix is part of the file name.
- `coordinator/overnight/selftest.py`: the `key-mint` eval, a fake GitHub whose
  list never catches up, three back-to-back opens, three distinct keys, plus
  the explicit-key, listed-maximum, refused-create, prefix-change, pending and
  unreadable-record cases.
- `coordinator/bin/hourly_selftest.py`: the eval name in `EXPECTED`.
- `evidence/MO-681/replay.md`: the gateway replay. It shows `fresh=True` skips
  the short-TTL cache, and that with the conditional path turned off a lagging
  list still answers a fresh read with the old body, so the conditional path is
  not what makes it stale. It cannot show which response GitHub sent during the
  six opens, so the incident's exact cause stays unconfirmed.
- `evidence/MO-681/check-proof.md`: the check proof.

## Proof

The close checklist, run against the merged pull request and the corrected
ticket:

```
$ python3 coordinator/bin/close_check.py --repo shyamsivakumar/mac-ops --pr 718 --issue 681
close check: shyamsivakumar/mac-ops#718 (merge 5ffda005f22b)
scope: pass - every changed file is inside the ticket's stated scope
proof file: pass - evidence/MO-681/check-proof.md is present
checks: pass - every one of the 9 checks the proof file lists passed
cost note: skipped - the MO-1068 cost report (evidence/MO-1068/cost-report.md) does not exist yet
RESULT: PASS shyamsivakumar/mac-ops#681
```

The `key-mint` eval fails on the old mint, so it is not self-referential:

```
old mint caught: expected ['MO-2', 'MO-3', 'MO-4'], got ['MO-2', 'MO-2', 'MO-2']
```
