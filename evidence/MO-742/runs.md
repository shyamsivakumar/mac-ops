# MO-742 runs

Command: `python3 evals/ladder/mine_traces.py --since 2026-11-13`

Output:

```
long_run: 123
loop: 188
rate_limit: 99
retry: 210
success_sample: 5
tool_failure: 463
pi sessions without a flag: 472
wrote evals/ladder/traces/flagged-2026-11-20.jsonl
```

The flagged file is `evals/ladder/traces/flagged-2026-11-20.jsonl` (gitignored, not committed). Every row has a distinct `run_id`.

## Known failures from the brief

- FOUND: gatekeep aborts on missing mac-ops issue #1131. `gatekeep.log` has 7 `gatekeep stopped: GitHub request failed: repos/shyamsivakumar/mac-ops/issues/1131/comments?per_page=100` lines, flagged `tool_failure`. `lanes.log` has `ITEM ERROR ... ticket gate 'shyamsivakumar/mac-ops#711'` (2026-11-20 06:32), flagged `tool_failure`. `decisions.md` records it at 2026-11-19 20:40 PT. `gatekeep.log` has no timestamps, so the gatekeep rows carry no time range.
- FOUND: API-floor ticks. 20 `rate_limit` rows come from `gatekeep.log` (consecutive lines merge into one run) ("below the API floor 1500", "optional reads stopped"), 18 from `ticks.log` and 10 from `gh-usage.jsonl` (minutes with 60 or more `gh` calls).

## Sample rows (source paths shortened)

```
{"run_id": "7811cd3a6271", "source": "~/Code/coordinator/queue/gatekeep.log", "start": null, "end": null, "rule": "rate_limit", "excerpt": "gatekeep skipped: below the API floor 1500 {'core': 1410, 'graphql': 4064}"}
{"run_id": "c71c85128276", "source": "~/Code/coordinator/loop/decisions.md", "start": "2026-11-19T20:40:00+00:00", "end": "2026-11-19T20:40:00+00:00", "rule": "rate_limit", "excerpt": "- 2026-11-19 20:40 PT | route | gatekeep aborts its pass on nonexistent tickets: each of its last three passes queued a gate and then stopped with `GitHub request failed: repos/shyamsivakumar/mac-ops/issues/1131/comments?per_page=100`. That issue does not exist (`gh api repos/shyamsivakumar/mac-ops/"}
{"run_id": "530c25136d5b", "source": "~/Code/coordinator/queue/gatekeep.log", "start": null, "end": null, "rule": "loop", "excerpt": "same line 3+ times: skip shyamsivakumar/mac-ops#157: router chain includes Claude"}
{"run_id": "599a7164ef78", "source": "~/.pi/agent/sessions/--Users-shyamsivakumar-.t3-worktrees-cairn-t3-eaf21d9e-7af24124bfaa341c--/2026-11-13T16-45-25-130Z_01a1d5cc-b509-7250-9", "start": "2026-11-13T16:45:25.130000+00:00", "end": "2026-11-13T19:00:19.904000+00:00", "rule": "long_run", "excerpt": "135 minutes, 151 tool calls"}
{"run_id": "28f42849163c", "source": "~/.pi/agent/sessions/--Users-shyamsivakumar-.t3-worktrees-strategy-replay-workbench-t3-016af9d2-92f09d67d58074f4--/2026-11-13T03-12-17-748Z_", "start": "2026-11-13T03:12:17.748000+00:00", "end": "2026-11-13T03:22:15.752000+00:00", "rule": "success_sample", "excerpt": "64 tool calls, no rule fired"}
```

## Time zone fix

`ticks.log`, `decisions.md` and `lanes.log` stamps without a trailing `Z` are America/Los_Angeles and are converted to UTC (stamps ending in `Z` are already UTC). Corrected row: the decisions.md entry "2026-11-19 20:40 PT" now has start `2026-11-20T04:40:00+00:00`, where it was `2026-11-19T20:40:00+00:00` when parsed as UTC.

```
{"run_id": "c71c85128276", "source": "~/Code/coordinator/loop/decisions.md", "start": "2026-11-20T04:40:00+00:00", "end": "2026-11-20T04:40:00+00:00", "rule": "rate_limit", "excerpt": "- 2026-11-19 20:40 PT | route | gatekeep aborts its pass on nonexistent tickets: each of its last three passes queued a gate and then stopped with `GitHub request failed: repos/shyamsivakumar/mac-ops/issues/1131/comments?per_page=100`.
```

## Redaction example

Input: `git clone https://exam:passwor@github.com/x/y.git`, `Authorization: Bearer abc123`, `password=foo`
Excerpt: `git clone [redacted]github.com/x/y.git`, `[redacted]`, `[redacted]`

## Gate fix (secrets in excerpts, bad records, fractional UTC)

Proof script: a pi session with 5 failed tool calls echoing `{"password": "hunter2"}`, one truncated JSONL line, and a `.123Z` stamp. Before = head 08cbf734 code, after = 7cc38185.

    BEFORE (no truncated line):
    rows: ['5 failed tool calls, first: bash failed: request failed: {"password": "hunter2"}']
    hunter2 leaked: True
    skipped: n/a
    ts: False
    BEFORE (truncated line):
    json.decoder.JSONDecodeError: Unterminated string starting at: line 1 column 15 (char 14)
    AFTER (truncated line):
    rows: ['5 failed tool calls, first: bash failed: tool_failure']
    hunter2 leaked: False
    skipped: {'bad pi record': 1}
    ts: True
