# Load tool lifecycle

- [Eval scorecard (hard stops and scorecards)](../evals.md).
- [Heavy admission, queue and pressure handling](heavy.md).
- [Governor sampling, floor, growth and local board admission](governor.md).
- [Restart of a board task whose agent died](restart.md).
- [Idle agents waiting for heavy admission](agent-heavy-wait-pause.md).
- [Install, migration and uninstall](installation.md).
- [Cursor startup and first-message delivery](cursor-input.md).
- [Pi startup and first-message delivery](pi-input.md).
- [Omp startup and first-message delivery](omp-input.md).
- [Omp Cursor turn retry](cursor-retry.md).

The [governor](../../.agents/skills/verify-governor/SKILL.md) and
[capacity](../../.agents/skills/verify-capacity/SKILL.md) skills name the
bounded checks and their limits. Native process checks and live controller
logs are also required.

The [Cursor input](../../.agents/skills/verify-cursor-input/SKILL.md) skill
covers buffered delivery ordering and the live terminal checks.
