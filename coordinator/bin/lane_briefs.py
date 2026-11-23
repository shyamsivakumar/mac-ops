"""This file owns the brief text lane threads receive, and prompt_paths holds changes to it."""

OPEN_FINDINGS_NONE = "Open critical or major findings: none"
OPEN_FINDINGS_INSTRUCTION = (
    "This is the last review round. The second-to-last line of your report must be exactly "
    f"`{OPEN_FINDINGS_NONE}` or `Open critical or major findings: <n>` (the count of critical "
    "and major findings still open), after your CHECK line and followed by the final VERDICT line.")

UNSTICK_BRIEF = """Type: design · gpt-6.1-sol (unstick orphaned tickets; Shyam 2026-11-14: "push on the rest of the backlog and complete it", "dont wait on anything", "no testing is needed")

These open tickets in {repo} were started, their builder finished, and there is no PR and no live thread: {list}. Each one holds up the tickets blocked behind it. Lane spec: /Users/shyamsivakumar/Code/coordinator/specs/lane.md. Standing decisions: /Users/shyamsivakumar/Code/coordinator/notes.md.

For EACH issue: read it, its comments (the `coordinator-ticket` receipt comments name the builder's T3 thread; read that thread's last report with `t3mcp call t3_thread_read '{"threadId":"<id>","view":"messages","limit":6}'`), and check origin/main. Before you close or re-cut an issue, re-read its open pull requests: `gh pr list --repo {repo} --state open --limit 200 --json number,body`, then match `Refs #<n>` exactly. The lane's snapshot can be older than a pull request opened minutes ago.

Two outcomes end the work on an issue at once, and both are finished, not unfinished:
- A pull request matches: report it and leave the issue untouched. It is not orphaned, so do not close or re-cut it.
- The lookup is incomplete (the command fails, or the list reaches the limit): report it and leave the issue alone.

Only an issue that is still a confirmed orphan after both checks goes on to exactly one of:
1. Already delivered on main: close it as completed with the commit or PR that delivered it.
2. Umbrella spec or map (not buildable itself): remove it as a blocker from its children (`gh issue edit <child> --remove-blocked-by <this>`), label it `stage:backlog`, comment that it closes when its children close.
3. Too big or stopped mid-way: cut the remaining work into at most two ordered tickets that each fit a 5-minute builder turn (12-section template in ~/.coordinator/tickets.json, Requires/Provides, Design fit, labels stage:todo,type:<type>,priority:<same>, keys after the repo's highest key), chain them with --add-blocked-by, repoint its children to the last new ticket, and close it as not planned naming the new tickets. If the builder left commits on a branch, name that branch as the base in the first new ticket.
4. Stopped on a question: answer it yourself from the ticket, notes.md and the testing waiver (device, live-service and owner testing are waived; never ask Shyam), post the answer under the heading `## Coordinator decisions (override the body)`, and label it `stage:todo`.

Every confirmed orphan must end closed, `stage:todo` and ready, or an umbrella in `stage:backlog`. An issue skipped for a matching pull request or an incomplete lookup is done for this pass: report it and move on, and do not come back to it. Start nothing and change no code. 15 minutes; if time runs short, finish the issues you can and list the rest.
Report one line per issue: number, action taken (or `skipped: matching PR #<n>` / `skipped: incomplete PR lookup`), new tickets.
"""

RECUT_BRIEF = """Type: design · {model} (re-cut an oversized pull request)

Pull request {repo}#{number} head {head} counts {lines} code lines in {files} code files. One ticket may hold at most {cap_lines} code lines in {cap_files} code files, counted the way the gate counts them.
Read the pull request with `gh pr diff {number} -R {repo}`. Cut the work into at most two ordered tickets, chained with Blocked by, and never create a third ticket. Each ticket should fit that cap; when a piece cannot fit, name the work to leave for `Left for later` in the pull request or the second ticket. Each new ticket's Context names the original pull request {repo}#{number} and head {head}.
Read a recent mac-ops ticket for the shape (for example `gh issue view 810 -R shyamsivakumar/mac-ops`) and fill every template section: Goal and why, Context, Scope and non-goals, Design fit, Blocked by, Acceptance and proof, CI, Must not cause, Data/secrets and stop conditions, Rollback, Gate, Finish. Add a `Proof command:` line.
Open each one with `ticket open --repo {repo} --title "<title>" --body-file <file> --label stage:todo,type:<type>,priority:<n>`; the tool mints the key, so never type a key and never use `gh issue create`. If the source pull request's ticket title carries `Parity <Pxx>`, each piece's title is `Parity <Pxx>.<k> · <title>`, numbered from 1. If `ticket open` refuses a body or a title, fix it and retry.
After the last ticket is open, comment once on the pull request: "Superseded by #<a>, #<b>, ..." naming the new tickets, and leave the pull request open. The lane or Shyam closes it.
Start nothing, change no code, and ask no one.
"""
