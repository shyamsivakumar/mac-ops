# MO-185/186 verification, 2026-11-12

Cockpit reads T3 and Approve queues a gated relay merge. The board never runs
GitHub's merge command itself. No dependencies or CI workflows were added.

## Findings and fixes

- The retired-call grep previously matched the absolute empq path. Both queue
  calls now resolve `empq` from PATH. `retired-grep.txt` records the actual empty
  output and exit 1 from `grep -rn 'emp_\|/bin/emp' empryo/mods/cockpit`.
- Deleted oldShells, window discovery/close and their callers, shell badges,
  the unreachable ops-panels path, and the obsolete Empryo session guard.
- Replaced merge stubs with fresh PR and separate review preflight. A completed
  claude-opus-5-5 run must end in VERDICT: PASS and CHECK the current full SHA
  and PR. Ascend repos refuse; SRW requires successful srw/agent-check.
- Approve and Approve all retain press-twice confirmation. The relay is queued
  with taskType worker (empq's MiniMax worker mapping), the PR repo's project,
  and exactly the squash merge command pinned by --match-head-commit.
  Same-head requests are deduplicated for the lifetime of the loaded module.
- Ready uses "Approve merge" and shows the relay plan in its action tooltip,
  or the refusal on the card. A fresh preflight runs again before queueing.
- Pending requests are listed once per live thread per load. A failed lookup
  labels that card "pending request unknown" without blanking the board.

## Repeatable proofs

Run `node evidence/MO-185/relay-probe.mjs`. It creates executable empq, gh and
T3 stubs in a temporary directory. It performs no live queue writes, merges
or sends. `relay-proof.json` records passing refusal cases, exact relay payload,
press-twice confirmation, same-head deduplication, and pending lookup isolation.

- `python3 scripts/mac_ops_fast_check.py`: passed; selected checks, not full suite.
  Output is `fast-check.txt`.
- `node --check` on every cockpit JavaScript file: passed.
- `herdr-app check empryo/mods/cockpit`: passed (`herdr-check.txt`).
- `git diff --check`: passed.
- One Luna Max read-only in-session reviewer round. Recognized the documented
  subscriptions/ Opus model prefix and added a stub probe. The suggested
  absolute empq path was not adopted: the task explicitly permits PATH and
  the installed live empq status probe passed. No Opus gate launched.
- Bounded deslop and no-comments diff review removed obsolete compatibility
  paths; no comments or dependencies added.

## Installed read-only proof and rollback

The previous installation was copied to
`~/.config/herdr-app/mods/cockpit.pre-mo186` before replacing its JavaScript.
`live-probe.mjs` allowlists T3 reads, gh pr view and empq status only.
`live-summary.json` and `live-proof.json` record exact equality of Running IDs
against stable before/after T3 listings and Ready preflight refusals.
`board.png` shows the native loaded board and Ready refusals. `app-status.json`
records no app errors. No real Approve, Reply, Settle or send was executed.

Restore the backup directory to roll back the local installation; revert the
PR to roll back source. The separate exact-head Opus gate remains required.
Stub proof does not prove a real relay merge, which was deliberately not run.
