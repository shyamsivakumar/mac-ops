# One gate on demand: `ticket gate`

`ticket gate <owner/repo>#<pr>` builds the review-gate brief for one pull
request and queues the gate thread. The coordinator used to write that brief
by hand, and one of those briefs went out with the pull request number and
the commit left blank.

The rules live in the coordinator `CLAUDE.md` sections "Review gate" and
"Ten minutes start to finish". `coordq gatekeep` runs the same rules over
every open pull request on its own schedule; `ticket gate` is the manual
path for one pull request.

## What it reads

- The pull request: its head sha, its base branch and the `Refs #n` issue.
- The issue: the ticket key in its title, checked against the key of the
  repository in `tickets.json`.
- The builder thread of the issue: the model its newest run ran.

## What it writes

The brief, with every value filled in, and the thread title
`<KEY>-<n> review #<pr> <sha8>`. The reviewer is Claude Opus 5.5
(`claudeAgent` / `claude-opus-5-5`), or Sol (`codex` / `gpt-6.1-sol`) when
the builder ran a Claude model. A builder whose model cannot be read leaves
the gate on Opus.

The brief asks the gate to read the diff only, to confirm the check of that
exact head (`srw/agent-check` success, or the pull request's
`Builder check: PASS <sha>` line) and to end with exactly one line,
`VERDICT: PASS` or `VERDICT: FAIL`. A personal repository merges on a pass
with `--match-head-commit <sha>`; an Ascend repository stops at the verdict.

The gate thread is queued through `coordq` at priority 400. The CLI never
merges: the merge is the gate thread's own step, and only after the check
and the verdict pass on that head.

## What it refuses

- The pull request is not open, or is a draft.
- The pull request body references no issue with `Refs #n`.
- The issue title carries a key of another repository.
- A gate for that pull request head is already queued, already running, or
  already ran. One head gets one gate: a second gate would try to merge a
  head that is merged already.
- Another gate for that pull request is running on this Mac.

## Flags

- `--print-brief` prints the brief and stops. It does not queue anything and
  does not look for a live gate.
- `--dry-run` prints the title, the reviewer and the `coordq` command it
  would run, and stops.

## Command

```
ticket gate shyamsivakumar/mac-ops#230 --print-brief
ticket gate shyamsivakumar/mac-ops#230 --dry-run
ticket gate shyamsivakumar/mac-ops#230
```
