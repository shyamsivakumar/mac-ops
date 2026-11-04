# Rules for every Empryo task

You run unattended. A coordinator agent reads your result and reports to Shyam.

- Work in the folder you were started in. Never commit to main or push to main directly.
- Never edit or weaken an existing test, check, fixture or proof script to make it pass. If one is wrong, say so in your report and leave it. New checks go in new files only when the task asks for them.
- Prove your work by running it: the repo's own tests, typecheck, build, or the real command. Say what you ran and what it printed.
- Before you report a coding task done, dispatch the `code-reviewer` agent with the task text and the base branch. Fix every critical and major finding, then dispatch it again. Stop after 3 review rounds and report what is still open. Include the last `VERDICT:` line in your report. Skip this for docs-only or config-only changes and say that you skipped it.
- Merges, deploys, secrets, paid actions and product decisions follow the repo's rules and the coordinator's instructions in your task. When unsure, stop and say what you need.
- End with a short report: what changed, what you ran and its result, the review verdict, and what is left.
