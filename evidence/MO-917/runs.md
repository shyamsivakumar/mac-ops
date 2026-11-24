# MO-917 runs

## Proof command, red on origin/main (2ea72fba)
```
/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file '/Users/shyamsivakumar/Code/mac-ops-worktrees/mo917-main/scripts/coord_wake_metrics.py': [Errno 2] No such file or directory
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/json/__init__.py", line 293, in load
    return loads(fp.read(),
  File "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
  File "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/json/decoder.py", line 337, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
  File "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/json/decoder.py", line 355, in raw_decode
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
exit=1
```

## Proof command, green on the branch
```
exit=0
```

## inbox eval of coordinator/overnight/selftest.py (branch selftest, run alone)

Red on origin/main code (the branch selftest copied over a clean origin/main worktree):
```
  File "<frozen importlib._bootstrap_external>", line 982, in get_code
  File "<frozen importlib._bootstrap_external>", line 1039, in get_data
FileNotFoundError: [Errno 2] No such file or directory: '/Users/shyamsivakumar/Code/mac-ops-worktrees/mo917-main/scripts/coord_wake_metrics.py'
```
Green on the branch:
```
PASS inbox
```

## One read-only run on the real logs, compared with the design doc

Command (reads the real launcher log, journal and ticks log; no inbox.db exists yet, so inbox fields are null):

```
python3 scripts/coord_wake_metrics.py --since 2026-11-21 --until 2026-11-23T20:54 --json
python3 scripts/coord_wake_metrics.py --since 2026-11-16 --until 2026-11-23 --json
```

| Quantity | Design doc | Script |
| --- | --- | --- |
| launcher runs, 21 Nov to 23 Nov 15:53 EST | 88 | 88 |
| failed (402) | 34 | 34 |
| NOOP | 41 | 41 |
| alert lines | 13 | 13 |
| runs a day | about 41 | 40.3 |
| count-format summaries, 16 to 22 Nov | 106 | 106 |
| of those, acted on nothing | 56 (52.8%) | 56 (0.528) |

Buckets for the 88 runs: failed 34, no_events 5, no_action 37, action 12, skipped 0, lock_skipped 0. The real tick.log has no `skip:` line yet (precheck is off), so the skipped bucket is exercised by the fixture only (1 skip line there).

Window 21 Nov to now (95 runs, the log has grown): failed 38, noop 43, alerts 14, 40.4 runs a day. Journal wake-class events 594, 0.397 duplicate rate on the (event, repo, pr, head, alarm) key. Wait from a wake-class journal row to the next launcher run: n 602, median 16.9 min, p90 27.6 (the doc's clock figure is 16.2 and 26.6 over a slightly different window and with alarm generations deduped). Lost events: 0 stuck, 0 fallback_acted, never_enqueued null (no GitHub list given and no inbox). No network call was made.

## Not measurable yet, left out on purpose

- Duplicate rate on the inbox side: T1 keeps no count of ignored inserts, so only the journal-side rate is reported.
- Event to action latency from the inbox (outbox sent_ts): reported when the tables hold data; the selftest covers it with one row.
- The GitHub reconciliation runs only with --reconcile-github or --github-prs FILE.
