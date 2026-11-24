## Red on origin/main (c032d3e9)
```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: no stash rule
exit 1
```

## Green on the branch
```
exit 0
```

## Launch paths that put AGENT-RULES in front of a brief

All paths end in `call()` (coordinator/bin/coordq:400-412), which prefixes the rules (`with_rules`, :396) to the message of every `t3_thread_launch` that `wants_rules` (:390: has a message, task type is not review, model is not a gate model, title has no review/critique/merge relay). Rules are read from `RULES_PATH` (:67, `~/.coordinator/AGENT-RULES.md`, installed by install_coordinator.py:30).

- Dispatch drain: reads rules at coordq:805-815, then `call(step["tool"], step["args"], rules)` at :831. Gets the rule.
- `ticket start` (builder launch): builds a launch payload and queues it with `coordq start` (coordinator/bin/ticket:1498). `cmd_start` checks the rules file reads (coordq:1006-1011) and queues; the drain above adds the prefix. Gets the rule.
- Refill: runs `ticket start` through coordq.py (:1285 area, refill at :1379+), so the same path. Gets the rule.
- Lane re-cut brief: `cmd_start` at coordq:2436 with `t3_thread_launch` and taskType design, then the drain. Gets the rule.
- `coordq create` (:1528): idle thread, refuses any message, so no brief to prefix. Not applicable.
- Gate and review launches (ticket:1901): skipped on purpose by `wants_rules` (review task type, gate model, or title). Does not get the rule; a reviewer does not build.
- Probe launch (coordq:1831): `t3_call` directly, scratch thread with "Reply with the word ok." Does not get the rule; not a builder.
- Lane fix rounds (coordq:2632 gate findings, ticket:2013 close-check findings): `t3_thread_send` into the existing builder thread. `call()` only prefixes `t3_thread_launch`, so a send carries no rules. The builder thread got the rule at its launch, so a fix round reaches a builder that already has it. A builder thread launched before this change and installed before the installer runs keeps the old rules until restarted.

## Tests that pin AGENT-RULES.md

No test pins its full text or size. Substring checks only: tests/test_gate_bar_convergence.py:79-80 (the Shyam question rule), tests/test_install_coordinator.py:798-811 (two phrases, plan target), selftest.py:429 (a path used as a changed-file case), and the prompt_paths and ticket_text_blockers tests (path names only). None is touched by the new line.
