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
  using the standard `CHECK: PASS <40-character SHA>` line. Ascend repos refuse;
  SRW accepts that exact-head review as allowed by the task.
- Approve and Approve all retain press-twice confirmation. The relay is queued
  with taskType worker (empq's MiniMax worker mapping), the PR repo's project,
  and exactly the squash merge command pinned by --match-head-commit.
  Same-head queued or ambiguous requests are deduplicated for the lifetime of
  the loaded module. Definite queue failures and project lookup refusals can retry.
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
The native screenshot is kept outside git because it includes unrelated
conversations. The prior board.png was removed from the current tree; its
earlier git history remains unchanged. `app-status.json`
records no app errors. No real Approve, Reply, Settle or send was executed.

Restore the backup directory to roll back the local installation; revert the
PR to roll back source. The separate exact-head Opus gate remains required.
Stub proof does not prove a real relay merge, which was deliberately not run.

## Failed re-gate follow-up

The review at 492d3fd8 reported no critical findings and two majors. The CHECK
parser now requires exactly one `CHECK: PASS <40-character SHA>` line matching
the fresh PR head, and the unused prBlocked method and import are deleted.
The existing stub proof now uses the standard format and rejects CHECK FAIL
with a PASS verdict. It also covers duplicate CHECK lines, SRW's exact-head
review alternative, retry after project or queue refusal, concurrent deduplication,
and retained ambiguous queue responses. All 20 cases pass without live mutations.

The later ad95be4 commit had already removed the unused UI destructuring and
stray blank line. Running the proof exposed a runStartOf cache lookup crash
when both cache and latestRunId were missing; the cache now must exist first.
The live probe was updated for that commit's read-only run lookups and removed
hubStatus API, and reads the installed hub source directly.

Before reinstalling, the complete previous installation was backed up to
`~/.config/herdr-app/mods/cockpit.pre-mo185-regate-20261112-110558`.
No gate, merge, send, reply or settle was launched. The exact-head review remains
pending for the new commit. Bounded deslop and no-comments diff review found no
new comments or further cleanup needed; pre-existing generated untracked files
were left untouched.

## Gate 3 follow-up

Gate 3 at 6a4df284 found that recentRuns.at(-1) selected the oldest run.
The merge reader, displayed model and vendor check now select the highest
ordinal. The merge reader only accepts that run's last assistant message.
A newest run that is not completed refuses with "Review still running";
an activeRunId also blocks approval. An older PASS cannot override a newer FAIL.

Removed the unused statusCheckRollup field from the PR lookup. Approve no
longer arms a card with a review block or stored queue refusal. A preflight
refusal can still retry. Approve all checks board freshness without binding
its action to the selected card. Deduplication still lasts until module reload.

The stub harness passes 28 cases, including older PASS/newer FAIL, newest
PASS with matching CHECK, newest running, stale newest CHECK, last-message
FAIL, and unordered run arrays with unrelated messages. It also verifies
blocked-card confirmation and the Approve all guard. No live relay was queued.

The fast check passed its selected checks. Node syntax passed on all eight
Cockpit, ops-panels and evidence JavaScript files. The retired-call grep was
empty (exit 1). Source and installed herdr-app checks passed, and installed
JavaScript matches source. gate3-install.json records the complete installation
backup made before copying. No new browser or live merge proof was attempted.

Bounded deslop removed the unused GitHub response field. No-comments diff
review found no added or touched comments. Pre-existing generated untracked
files remain untouched. Gate 3 remains FAIL on its reviewed head; no new gate
was launched. A separate exact-head review remains required for the new head.
