These standing rules come first; the ticket brief that follows overrides them where they differ.

- T3 Code only. Never call `emp`; it is retired.
- Work in the folder you were started in. Never push to main, force push, or use `--no-verify`.
- CI is agent checks only: no Woodpecker, no GitHub Actions.
- The Coordinator runs the Opus gate. You run one in-session reviewer round, then report.
- A turn lasts at most 10 minutes. Never end a turn with only a plan; do the work or name the blocker.
- Never read, print or commit secrets or `.env` files.
- Never edit or weaken an existing test or check to make it pass; say so in your report instead.
- Reference tickets as `Refs #<n>`, never `Fixes`, `Closes` or `Resolves`.
- Open pull requests as READY, never as draft, unless the brief says draft.
- In strategy-replay-workbench, do not run the heavy `scripts/check.sh` script; the Mac check publisher posts `srw/agent-check` on ready PRs. In other repos, run the repo's full local check and put `Builder check: PASS|FAIL <full sha>` in the PR body.
- When you must ask Shyam, give a short summary plus a kpane diagram.
