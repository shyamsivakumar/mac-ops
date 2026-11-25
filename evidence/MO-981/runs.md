# MO-981 runs

## Ticket proof command

On origin/main (coordq taken from `git show origin/main:coordinator/bin/coordq`):

```text
KeyError: 'held_gate_thread'
exit 1
```

On the branch head (code commit):

```text
exit 0
```

## Selftest

`held_merge()` in `coordinator/overnight/selftest.py` run alone with a temp `COORDQ_DIR` and `COORD_JOURNAL_DIR`.

- Against the origin/main coordq: `AttributeError: module 'fixture_coordq_main' has no attribute 'held_gate_thread'`.
- On the branch: `PASS`.

The brief pins in `tests/test_prompt_paths.py`, `test_gate_fast_forward.py`, `test_check_proof.py`, `test_gate_bar_convergence.py` and `test_close_check.py` still pass unchanged (208 tests, none edited).

## Read-only replay over November

`~/.local/state/coordinator/journal/events-2026-11.jsonl` (52 `merge_held` rows, 562 `t3_thread_send` enqueues) and the live
`dispatch-receipts.json`. For each send, `held_gate_thread(row.thread, receipts, merge_held rows with ts before the send)`.

```text
refused by held_gate_thread: 2
15640 MO-967 merge 008b3ea5            shyamsivakumar/mac-ops#967 (loop code hold)  tick  mcp:launch:c23d3847...
15751 mcp:launch:4ee65707...           shyamsivakumar/mac-ops#980 (loop code hold)  tick  mcp:launch:4ee65707...
```

- 15751 (title is the thread id, no merge key or title): "Finish this gate ... Run the merge approval step for this exact head". Read with `t3mcp call t3_thread_read` (read-only). Refusing it is right; this is the send that merged #980.
- 15640 (`MO-967 merge 008b3ea5`): "Finish the merge now with --match-head-commit 008b3ea5...". Refusing it is right; it is a merge order sent to a held gate thread.
- Of 562 sends, 18 went to a gate thread (3,612 gate threads in the receipts). The other 16 were sent before any hold on that head (or on a different head), and stay allowed. No `cmd_gate`, `cmd_fix`, close-check nudge or missing-verdict nudge sent to a gate thread after a hold in November, so no legitimate send is refused.
- Receipts are the live file, not the file as of each send. Gate thread ids are the same form in receipts and sends (`mcp:launch:<64 hex>`; the sends to other `mcp:<id>` threads are builder threads and match no gate key).
- Message text is not in the journal (title only) and not in the queue file. Only the two refused threads were read through `t3_thread_read`. `held_command` was therefore replayed only on those two messages: neither holds the string `gh pr merge`, so only the thread check refuses them.

## Probes

- Receipt keys: `gate:<repo>#<n>:<head>` with any `:suffix` (`:lane`, `:gate:main:lane`, `:astra2`, `:swap`, `:retry`, `:regate:...`); `base:`, `brief:`, `merge-pass:`, `ticket:` keys never match. Repo and head compare case-insensitively. A thread that maps to several heads is refused only when a held head maps to it.
- Dispatchable tools are `t3_thread_launch` and `t3_thread_send`. `t3_queue`, attachments and configure are not dispatchable, so `cmd_start` already refuses them before this check.
- Unreadable receipts (`load_receipts` returns `{}`), non-dict receipts, non-string keys and values, non-string thread or message, and journal rows missing data or head do not crash.
- The journal is scanned only for a send (a `threadId` string) or a message holding `gh pr merge`, never for a plain launch.
- A gate brief for a lane repo never holds `gh pr merge`; a reviewer-mode brief for an unheld head passes (the command names a head with no hold row).
