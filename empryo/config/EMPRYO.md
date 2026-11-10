# Rules for every Empryo task

You run unattended. A coordinator agent reads your result and reports to Shyam.

- Work in the folder you were started in. Never commit to main or push to main directly.
- Never edit or weaken an existing test, check, fixture or proof script to
  make it pass. If one is wrong, say so in your report and leave it, unless
  your brief quotes Shyam approving that exact edit; then change only what
  he approved and show each changed line. New checks go in new files only
  when the task asks for them.
- Exception (Shyam, 2026-11-09): tests, checks, fixtures and proof
  scripts that this task's own branch created (absent from the base
  branch, per `git diff --diff-filter=A <base>`) may be edited without
  a per-edit quote, as long as no check gets weaker and every changed
  line is listed in the PR. Anything on the base branch still needs
  Shyam's quoted approval of the exact edit.
- Build each change in the module that owns it, with clean separation of
  concerns (Shyam, 2026-11-09). Do not bolt a feature on: no parallel
  paths, special cases in the wrong layer, or shims. If the change can't be
  built naturally in the existing structure, stop before coding and report
  the refactor you recommend instead.
- Prove your work by running it: the repo's own tests, typecheck, build, or
  the real command. Say what you ran and what it printed.
- Never use computer use or host-script tools in a task.
- Before you report a coding task done, dispatch the `code-reviewer` agent
  with the task text and the base branch. Fix every critical and major
  finding, then dispatch it again. Stop after 3 review rounds and report
  what is still open. Include the last `VERDICT:` line in your report. Skip
  this for docs-only or config-only changes and say that you skipped it.
- Never instruct a read-only reviewer or subagent to run proofs or
  commands. Reviewers verify the builder's proof output and say
  'not independently rerun' when they cannot execute.
- Never reference the root checkout or another repo's paths in dispatch
  texts or commands; worktrees are self-contained (install dependencies
  in the worktree first).
- Merges, deploys, secrets, paid actions and product decisions follow the
  repo's rules and the coordinator's instructions in your task. When unsure,
  stop and say what you need.
- When your task text starts with `Ticket: <GitHub issue URL>`, that issue
  is your ticket. Reference it in PRs and commits as `Refs #<n>` (or
  `Refs owner/repo#<n>` from another repo). Never use `Fixes`, `Closes` or
  `Resolves`: only the coordinator closes a ticket, after the review gate
  passes. Don't edit the issue or its labels.
- End with a short report: what changed, what you ran and its result, the
  review verdict, and what is left.

Dev servers and previews use the port block in your task text
("Your port block: A-B"): those ten ports are yours. The shell does not
export `EMP_PORT_BASE`, so type the number. Before trusting a page on any
port, check which process owns the port and which directory it runs from
(`lsof -nP -iTCP:<port> -sTCP:LISTEN`, then `lsof -p <pid> | grep cwd`).
Never run `git stash` or switch branches in a checkout another task uses.
