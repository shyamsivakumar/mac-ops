# MO-971 runs

## Ticket proof

Command (from the ticket, `HOME=/nonexistent`, run at the repo root):

```text
HOME=/nonexistent python3 -c "import runpy,sys;sys.path.insert(0,'coordinator/bin');sys.path.insert(0,'coordinator/overnight');s=runpy.run_path('coordinator/bin/tick_health.py',run_name='p');h={'ts':0,'event':'merge_held','repo':'o/r','pr':7,'head':'a'*40,'data':{'reason':'loop code hold'}};f=s['held_alarm'];assert 'o/r#7' in f([h],now=7*3600,hours=6) and not f([h],now=3600,hours=6) and not f([h,{**h,'event':'merged','ts':9}],now=7*3600,hours=6);assert callable(s['idle_alarm'])"
```

Red on origin/main (a15ec9cd, a scratch worktree), exit 1:

```text
  File "<string>", line 1, in <module>
KeyError: 'held_alarm'
```

Green on the branch head, exit 0 (no output).

## Selftest eval `stop-rules`

Added to `coordinator/overnight/selftest.py` and to `EXPECTED` in `coordinator/bin/hourly_selftest.py`.
Run alone with a temp `COORD_JOURNAL_DIR`: on the branch it prints `ok`; with the new selftest copied onto origin/main code it fails with
`AttributeError: module 'tick_health' has no attribute 'held_alarm'`.
Cases: hold older and newer than the limit, `prompt hold`, other hold reasons, `merged` and `merged_outside_lane` by PR, a newer head superseding a hold, 7-day stop, unset, empty, NaN, negative, zero and text limits for both rules, bad rows, idle with a via_tick row inside the run window of the oldest counted tick, a later row for the FAIL PR, fewer ticks than the count, FAIL older than 7 days, tick.log parsing (multi-line reply, exit=1, killed line, year, EDT and EST for the repeated 01:30 on 1 Nov), the switch off reading nothing (`journal_rows` raises if called), a journal with two bad lines.

## Speed

Live journal `events-2026-11.jsonl`, 9.3 MB, 19,952 lines, read-only:
`journal_rows` 0.023 s (4,140 rows kept after the prefilter), whole `stop_rules_alarm()` with the switch on 0.031 s, off returns "" with `open` patched to raise.

## Replay over the live journal and tick.log, 23 to 25 Nov (read-only)

Method: every 15 minutes from 23 Nov 00:00 local to now, call `held_alarm` and `idle_alarm` with only the rows and finished ticks that existed at that moment. Script: `evidence/MO-971/replay.py`.
Limits: held at 4, 6, 12 hours; idle at 6, 8, 12 ticks.
Caveat: `via_tick` rows exist only from 23 Nov 20:32, so an idle verdict before that time cannot be trusted either way. The tick.log has 50 finished ticks (exit=0) since 23 Nov 00:00.

```text

held at 4: 2 alert(s)
  from 23 Nov 00:00 to 25 Nov 01:15 | ALARM: shyamsivakumar/sams-llm-wiki#244 held 14.1 h (prompt hold), no merge since
  from 23 Nov 03:15 to 23 Nov 09:00 | ALARM: shyamsivakumar/mac-ops#887 held 4.1 h (loop code hold), no merge since

held at 6: 2 alert(s)
  from 23 Nov 00:00 to 25 Nov 01:15 | ALARM: shyamsivakumar/sams-llm-wiki#244 held 14.1 h (prompt hold), no merge since
  from 23 Nov 05:15 to 23 Nov 09:00 | ALARM: shyamsivakumar/mac-ops#887 held 6.1 h (loop code hold), no merge since

held at 12: 1 alert(s)
  from 23 Nov 00:00 to 25 Nov 01:15 | ALARM: shyamsivakumar/sams-llm-wiki#244 held 14.1 h (prompt hold), no merge since

idle at 6: 1 alert(s)
  from 24 Nov 01:15 to 24 Nov 04:15 | ALARM: 6 finished ticks did nothing; gate FAIL waiting on shyamsivakumar/sams-llm-wiki#254

idle at 8: 1 alert(s)
  from 24 Nov 02:15 to 24 Nov 04:15 | ALARM: 8 finished ticks did nothing; gate FAIL waiting on shyamsivakumar/sams-llm-wiki#254

idle at 12: 0 alert(s)

via_tick rows: 155 first at 23 Nov 20:32
finished ticks since 23 Nov: 50
```
