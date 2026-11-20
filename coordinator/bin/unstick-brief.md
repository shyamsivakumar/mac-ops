Type: design · gpt-6.1-sol (unstick orphaned tickets; Shyam 2026-11-14: "push on the rest of the backlog and complete it", "dont wait on anything", "no testing is needed")

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
