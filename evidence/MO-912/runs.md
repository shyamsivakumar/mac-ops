# MO-912 runs

## Producer id sites checked on origin/main 2ea90a59

All eleven listed ids have both a raise and a withdraw site (lane_driver.py reconcile_prompt_items, clear_gate_round_decision, merge-pass 1543; coordq 2407 and 2203; stall.py; factory-watchdog and factory-zero-merge; hourly_selftest.py line 69 rewrites the card away on a passing run). None dropped.

## Proof on origin/main (red)

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: ((2, 2), ['lane-gate-rounds-o-r-1', 'merge-mo-9'])
exit 1
```

## Proof on the head (green)

```
exit 0
```

## Temp-dir scenario (decisions board plus owner board, actor scn)

```
5bc891d69875 fdf8073038a0 
$ board.py list
lane-gate-rounds-o-r-1	t lane-gate-rounds-o-r-1
herdr-build-x-5	t herdr-build-x-5
merge-mo-1	t merge-mo-1
factory-zero-merge-MO-3	owner card
exit 0
5bc891d69875 fdf8073038a0 
$ board.py patch lane-gate-rounds-o-r-1 title=x
board: lane-gate-rounds-o-r-1 is owned by its producer; only it withdraws the card
exit 1
$ board.py raise {"id":"prompt-merge-mo-9","group":"Coordinator","title":"forge"}
board: prompt-merge-mo-9 is owned by its producer; only it withdraws the card
exit 1
$ board.py remove lane-gate-rounds-o-r-1 merge-mo-1
board: lane-gate-rounds-o-r-1 is owned by its producer; only it withdraws the card
exit 1
5bc891d69875 fdf8073038a0 
$ board.py raise {"id":"wiki-238-a","group":"Coordinator","title":"agent card"}
exit 0
$ board.py patch wiki-238-a title=changed
exit 0
$ board.py patch wiki-238-a id=zzz
board: id=zzz is not a field to patch
exit 1
$ board.py patch nope-1 title=x
board: nope-1 is not on the board
exit 1
$ board.py remove wiki-238-a
exit 0
$ board.py remove herdr-build-x-5
exit 0
$ board.py raise {"id":"jobs-MO-77","group":"Coordinator","title":"owner board"}
exit 0
$ board.py remove jobs-MO-77
exit 0
$ board.py remove factory-zero-merge-MO-3
exit 0
$ board.py list
lane-gate-rounds-o-r-1	t lane-gate-rounds-o-r-1
merge-mo-1	t merge-mo-1
exit 0
--- journal
board_refused scn patch lane-gate-rounds-o-r-1 None
board_refused scn raise prompt-merge-mo-9 None
board_refused scn remove lane-gate-rounds-o-r-1 None
alarm_raised alarms None None wiki-238-a
board_cli scn raise wiki-238-a None
board_cli scn patch wiki-238-a None
board_refused scn patch wiki-238-a None
alarm_withdrawn alarms None None wiki-238-a
board_cli scn remove wiki-238-a None
alarm_withdrawn alarms None None herdr-build-x-5
board_cli scn remove herdr-build-x-5 None
alarm_raised alarms None None jobs-MO-77
board_cli scn raise jobs-MO-77 None
alarm_withdrawn alarms None None jobs-MO-77
board_cli scn remove jobs-MO-77 None
alarm_withdrawn alarms None None factory-zero-merge-MO-3
board_cli scn remove factory-zero-merge-MO-3 None
```
