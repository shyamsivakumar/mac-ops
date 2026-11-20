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
the gate on Opus, unless the builder thread is still running: then the gate
takes Sol, because a live builder may be Claude and two Claude threads must
not run at once.

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

## Prompt, skill and playbook changes

A prompt change never auto-merges (Shyam, 2026-11-17). Before the brief is
built, `ticket gate` reads the paths the pull request changed and compares
them with the list in `coordinator/bin/prompt_paths.py`: `AGENT-RULES.md`,
`answer_format.py`, `gate_bar.py`, `gate_findings.py`, `gate_policy.py`, `playbook.md`,
`code-reviewer.md`, any `SKILL.md`, and anything under a `skills/` or
`prompts/` directory.

When one path matches, the brief's heading says `review only`, the merge
order becomes `do not merge ... Shyam merges a passing one himself`, the
fast-forward is left out, and the brief closes no issue. A pull request that
only changes code keeps the merge order. A renamed file counts under both
names, so moving prompt text out of `prompts/` still holds it. A file list
GitHub cannot give, or one shorter than the pull request's own changed-file
count (the files endpoint stops at 3,000), is unknown: the read is retried
and then the gate refuses, because a brief built without the list could
order a merge of prompt text. The count is read from the pull request itself
when the caller holds none. A list that can never be completed, because the
pull request is bigger than the 3,000-entry cap, falls back to the complete
diff: the merge base's tree and the head's tree are compared and every path
that differs is read the same way, so a huge pull request of ordinary code
still merges.

A file list GitHub cannot give is not code: the read is retried, and a list
still unknown defers the gate instead of building a brief. A brief written
without the list could order a merge of prompt text, so an unreadable list
never reads as clear.

The lane driver reads the same list before it merges a passing pull request:
on a prompt change it merges nothing and writes one item to the decisions
board asking Shyam to merge it. A dry run writes no item, and an unreadable
list defers the pull request to the next run.

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
