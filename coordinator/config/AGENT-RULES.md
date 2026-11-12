These standing rules come first; the ticket brief that follows overrides them where they differ.

- T3 Code only. Never call `emp`; it is retired.
- Work in the folder you were started in. Never push to main, force push, or use `--no-verify`.
- CI is agent checks only: no Woodpecker, no GitHub Actions.
- The Coordinator runs the Opus gate. You run one in-session reviewer round, then report.
- A turn lasts at most 10 minutes. Never end a turn with only a plan; do the work or name the blocker.
- Never read, print or commit secrets or `.env` files.
- Never edit or weaken an existing test or check to make it pass; say so in your report instead.
- Reference tickets as `Refs #<n>`, never `Fixes`, `Closes` or `Resolves`.
- When you must ask Shyam, give a short summary plus a kpane diagram.
