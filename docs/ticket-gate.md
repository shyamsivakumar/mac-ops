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

## What it writes

The brief, with every value filled in, and the thread title
`<KEY>-<n> review #<pr> <sha8>`. Every gate runs on Astra (`codex` /
`gpt-6-astra`), whatever built the pull request, so the CLI reads no builder
model. The queue's one failover, Opus (`claudeAgent` / `claude-opus-5-5`),
lives in `coordq` and is used only after an Astra gate died on a quota or a
rate limit.

The brief asks the gate to read the diff only, to confirm the check of that
exact head (`srw/agent-check` success, or the pull request's
`Builder check: PASS <sha>` line) and to end with exactly one line,
`VERDICT: PASS` or `VERDICT: FAIL`. A personal repository merges on a pass
with `--match-head-commit <sha>`; an Ascend repository stops at the verdict.

The gate thread is queued through `coordq` at priority 400. The CLI never
merges: the merge is the gate thread's own step, and only after the check
and the verdict pass on that head.

A personal repository closes its ticket in the same step. After the merge
produced a merge commit, the brief tells the gate to run `gh issue close
<n> -R <repo> --comment "VERDICT: PASS. Merged via #<pr> (<merge commit
sha>)."` so the board stops showing finished work as open. The merge
commit is the one the gate reported, or the one `gh pr view <pr> --json
mergeCommit` gives. On a failed verdict, or when the merge did not happen,
the brief closes nothing. An Ascend repository stops at the verdict and
closes nothing either.

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
