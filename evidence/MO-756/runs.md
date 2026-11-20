# MO-756 runs

## Proof command, origin/main (red)
```
KeyError: 'escaped_merges'
```

## Proof command, branch (green)
```
{'r/x#1': 'fix'}
```

## Real 7-day count, mac-ops, merges 2026-11-13 to 2026-11-20 (read-only gh, adapted from the proof command)

Fix links come from merged PRs up to 2026-11-27; reopen events from the issue events API (one reopen, #378, matched no merge). Script ran escaped_merges on the real gh data.

```
merges 255 escaped 7
fix shyamsivakumar/mac-ops#203 Read the board and open pull requests into overnight intake records (R
fix shyamsivakumar/mac-ops#245 Overnight T3c: Intake orders the board (Refs #178)
fix shyamsivakumar/mac-ops#256 MO-244 · coordq fix sends the findings for one head only once
fix shyamsivakumar/mac-ops#262 MO-214 · Overnight T6: Evidence rule for done items
fix shyamsivakumar/mac-ops#308 Reclaim a dispatch reservation whose launch finished before it was see
fix shyamsivakumar/mac-ops#310 MO-267 · Cap gatekeep's re-gate of a dead head and back off between re
fix shyamsivakumar/mac-ops#408 Keep lane passes running after item command failures
old reverted []
```
