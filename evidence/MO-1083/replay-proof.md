# Replay proof: a verdictless gate falls back, a provider error blocks

The real CLI, `coordinator/bin/coordq gatekeep`, in a temporary queue
directory with a stub `gh` and a stub `t3mcp`. The gate run it reads is the
recorded failure in `tests/fixtures/gate/codex-astra-no-credits.json`
(codex gpt-6.2-astra, failed, "no credits left on this plan; it resets in 30
minutes"). Nothing here touches `~/Code/coordinator/queue`.

The chain under test is `codex gpt-6.2-astra` then `claudeAgent
claude-opus-5-5`.

## 1. A head whose gate died without a verdict moves down once

Head `a…` is recorded as gated, and its gate thread failed with no verdict.

```
$ coordq gatekeep --config <tmp>/tickets.json
regating o/r#7: aaaaaaaa (gate died without a verdict)
queued gate:o/r#7:aaaa… reviewer claudeAgent claude-opus-5-5
```

`queue/reviewers-blocked.json` then holds the reviewer that could not run,
until the reset time its error names (30 minutes), and `dispatch.log` holds
one line:

```
2026-11-17 21:27:39 reviewer codex:gpt-6.2-astra blocked until 2026-11-17 21:57:39
```

## 2. A new head starts on the next reviewer while the block lasts

Head `b…` has never been gated:

```
$ coordq gatekeep --config <tmp>/tickets.json
queued gate:o/r#7:bbbb… reviewer claudeAgent claude-opus-5-5
```

## 3. The block lifts after its window, once

The block record is aged past its `until`, and head `c…` arrives:

```
$ coordq gatekeep --config <tmp>/tickets.json
queued gate:o/r#7:cccc… reviewer codex gpt-6.2-astra
```

`dispatch.log` gained one line, and `queue/reviewers-blocked.json` is `{}`:

```
2026-11-17 21:27:43 reviewer codex:gpt-6.2-astra unblocked
```

## 4. With every reviewer blocked, the head waits

Both chain members blocked, head `d…` arrives:

```
$ coordq gatekeep --config <tmp>/tickets.json
defer o/r#7: every gate reviewer is blocked
```

No queue item was written for `d…`; the items in `queue.json` are the retry
of `a…` and the gates for `b…` and `c…` only.

## The same behaviour under test

`python3 -m unittest tests.test_gate_reviewer_fallback` covers the same four
cases plus a verdict run that is never retried, a run that records no model,
one move down per head, one log line per block, a run that answered before it
failed (no block), and a dry run that blocks nothing. On the previous head
the module fails 6 tests and errors on 8.

## Round-one fixes on #536

Two runtime defects in the gate fallback were fixed at 4c0b3e2, and the same
replay module covers both.

A head that a blocked Astra sent to Opus, and whose run died before recording
a model, is now attributed to the reviewer it was launched on. The old run
blocked Astra and could queue the same head on Opus again; the new run blocks
Opus, and with nothing left below Opus the head is given up and nothing is
queued. `coordq gatekeep` also writes the launch reviewer into `gatedHeads`
when it queues a gate.

A provider error is now a refusal only when it names the provider's own error
code or an explicit HTTP status. `worker 14031 exited` holds the digits of
403 and no longer blocks a reviewer.

```
$ python3 -m unittest tests.test_gate_reviewer_fallback
Ran 24 tests in 2.988s
OK
```
