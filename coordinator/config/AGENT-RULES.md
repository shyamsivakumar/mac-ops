These standing rules come first; the ticket brief that follows overrides them where they differ.

- T3 Code only. Never call `emp`; it is retired.
- Work in the folder you were started in. Never push to main, force push, or use `--no-verify`.
- CI is agent checks only: no Woodpecker, no GitHub Actions.
- The Coordinator runs the Astra gate on the exact PR head. Opus is allowed only when Astra's quota is exhausted; other failures do not permit Opus fallback. You run one in-session reviewer round, then report.
- Target 5 minutes per builder turn; 10 minutes is the normal ceiling. Log runs past 10 minutes as mis-sized in `loop/caps.log`. Stop runs past 20 minutes and return the ticket to the Coordinator for re-cut. Never end a turn with only a plan; do the work or name the blocker.
- Start the builder clock after worktree bootstrap. Run each shell command under `timeout 300`; repository bootstrap gets `timeout 600`. Never loop on retries or sleeps.
- `WAITING: heavy busy` is resumable, not an attempt. Pause the builder clock while heavy is busy; the lane resends the turn when heavy frees.
- The coordinator's brief is the approval for everything it names. Do not stop to ask for approval of a plan that stays inside the brief; this overrides contractor-gate and similar skills. Stop only on a stop condition the brief names or a hard limit.
- Never read, print or commit secrets or `.env` files.
- Never edit or weaken an existing test or check to make it pass; say so in your report instead.
- Reference tickets as `Refs #<n>`, never `Fixes`, `Closes` or `Resolves`.
- Open pull requests as READY, never as draft, unless the brief says draft.
- In strategy-replay-workbench, do not run the heavy `scripts/check.sh` script; the Mac check publisher posts `srw/agent-check` on ready PRs. In other repos, run the repo's full local check and put `Builder check: PASS|FAIL <full sha>` in the PR body.
- When you must ask Shyam, give a short summary plus a kpane diagram.
