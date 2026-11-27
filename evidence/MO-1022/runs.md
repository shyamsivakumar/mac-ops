# MO-1022 runs

Proof: `bash evidence/MO-1022/proof1022.sh <root>`.
`<root>` holds `coordinator/bin/coordq`.
It builds a temp COORDQ_DIR, a fake t3mcp and a temp T3 database. config.json has
`spendCapTokens` 1000 and `stallMinutes` 30. Card 1 has 5000 tokens, card 2 has
10 tokens and is fresh, card 3 has 10 tokens and is 2 h idle. It runs
`coordq spend`.

## origin/main (red)

```text
--- spend run
usage: coordq [-h]
            {start,create,list,drop,status,wait,waits,dispatch,gatekeep,gate,fix}
            ...
coordq: error: argument cmd: invalid choice: 'spend' (choose from ...)
exit 2
--- status stuck
[]
```

## branch head (green)

```text
--- spend run
stop o/r#1 th-over: spend cap: 5000 tokens, cap 1000
stop o/r#3 th-stalled: stall: no progress for 120 min, limit 30
exit 0
--- interrupt calls
t3_thread_interrupt {"threadId": "th-over", "stop": true}
t3_thread_interrupt {"threadId": "th-stalled", "stop": true}
--- second run, interrupt count
2
--- status stuck
['o/r#1 th-over spend cap: 5000 tokens, cap 1000',
 'o/r#3 th-stalled stall: no progress for 120 min, limit 30']
```

Card 2 (under the cap, fresh) is never stopped. The second run stops nothing
more (interrupt count stays 2).
