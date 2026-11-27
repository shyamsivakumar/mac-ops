# MO-1022 runs

Run: `bash evidence/MO-1022/proof1022.sh <dir with coordinator/bin/coordq>`.
It builds a temp COORDQ_DIR, a fake t3mcp and a temp T3 database. config.json has
`spendCapTokens` 1000 and `stallMinutes` 30. The fake thread list has 2 pages.
Page 1 holds card 2 (10 tokens, fresh) and card 3 (10 tokens, idle 2 h). Page 2
holds card 1 (5000 tokens). The script first runs `coordq spend` with page 2
unreadable, then with page 2 readable.

## origin/main (red)

`coordq: error: argument cmd: invalid choice: 'spend'`, exit 2.

## Previous head 7d0fe65b, one page only (red for the paging fix)

```text
--- page 2 unreadable: nothing stopped
stop o/r#3 th-stalled: stall: no progress for 120 min, limit 30
exit 0
interrupt count: 1
--- spend run (over-cap card on page 2)
exit 0
--- interrupt calls
t3_thread_interrupt {"threadId": "th-stalled", "stop": true}
```

Page 2 is never read: the over-cap card is missed, and a partial view is acted on.

## Branch head (green)

<!-- markdownlint-disable MD013 -->
```text
--- page 2 unreadable: nothing stopped
spend: cannot read every thread, nothing stopped: page 2 unreadable
exit 1
interrupt count: 0
--- spend run (over-cap card on page 2)
stop o/r#3 th-stalled: stall: no progress for 120 min, limit 30
stop o/r#1 th-over: spend cap: 5000 tokens, cap 1000
exit 0
--- interrupt calls
t3_thread_interrupt {"threadId": "th-stalled", "stop": true}
t3_thread_interrupt {"threadId": "th-over", "stop": true}
--- second run, interrupt count
2
--- status stuck
['o/r#1 th-over spend cap: 5000 tokens, cap 1000', 'o/r#3 th-stalled stall: no progress for 120 min, limit 30']
```
<!-- markdownlint-enable MD013 -->

Card 2 (under the cap, fresh) is never stopped. The second run stops nothing more.
