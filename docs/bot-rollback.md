# One-command rollback for Bot 1 and Bot 2

`scripts/bot_rollback.py` rolls a bot back to the rollback SHA that the
promotion path recorded for it, and then checks that the bot is healthy. The
dry run is the default: it prints the exact steps for every bot and changes
nothing.

```sh
python3 scripts/bot_rollback.py --dry-run
python3 scripts/bot_rollback.py --dry-run --bot bot1
python3 scripts/bot_rollback.py --execute --bot bot1
```

## Where the rollback SHA comes from

The promotion path moves a bot by pushing the new commit to the ref that
carries the bot's live commit. GitHub keeps a push record for that ref, and
each record holds the commit the ref held before the push (`before`). The
command reads the latest push record with `gh api repos/{owner}/{repo}/activity`
and takes its `before` as the rollback SHA, but only when the record's `after`
is the live commit. A promotion that advanced the ref across several commits
in one push still records the commit it moved from, so the rollback SHA is
right even when the live commit's parent is an intermediate commit. A record
that ends somewhere else, or a history that cannot be read, is reported as a
problem instead of being guessed.

For a bot whose live commit is not carried by a ref in the repository, the
config pins the SHA instead, in `rollbackSha`.

## The bot config

Which bot lives on which ref, which commands roll it back and which URL says
it is healthy are facts about the bots, so they live in one file,
`config/bot-rollback.json`. The command reads that file and never writes it.

```json
{
  "schemaVersion": 1,
  "bots": [
    {
      "id": "bot1",
      "label": "Bot 1, the paper-live trader",
      "repository": "~/Code/strategy-replay-workbench",
      "liveRef": "origin/paper-live",
      "rollbackSha": null,
      "rollbackCommands": [
        ["node", "scripts/srw_promote_paper_live.cjs", "--break-glass-rollback", "{sha}"]
      ],
      "healthUrlEnv": "BOT1_HEALTH_URL",
      "healthPath": "/health",
      "healthMustShowSha": true,
      "healthTimeoutSeconds": 300
    }
  ]
}
```

- `repository` is the checkout the bot lives in. The rollback and the health
  check run there, so a relative path in them resolves there.
- `liveRef` is the ref that carries the live commit.
- `rollbackSha` pins the rollback SHA. When it is null, the command reads the
  SHA from the ref's push history.
- `rollbackCommands` are the commands that roll the bot back, in order. The
  token `{sha}` is where the recorded SHA goes; a command without the token
  gets the SHA as its last argument.
- `healthUrlEnv` names the environment variable that holds the base URL of the
  bot's health endpoint, and `healthPath` the path under it. The health check
  is `curl -fsS <url><path>`. A bot that is checked by a script instead
  names it in `healthCommand`.
- `healthMustShowSha` says the bot's deployed-revision field has to equal the
  rollback SHA. `healthShaField` names that field in the JSON health answer
  (a dotted path, `sourceSha` by default). The command keeps asking until the
  field matches, up to `healthTimeoutSeconds`. The SHA appearing in another
  field, such as `previous`, does not count.

## What the dry run prints

For each bot: the repository, the live ref and the commit it points at, the
recorded rollback SHA, and one line per step with the exact command. A step the
config does not record prints as `not recorded`, so an unresolved bot still
shows every step it lacks. The health URL is never printed: the health step
names the environment variable that holds it, because the value may carry
credentials. Output from the commands is scrubbed of the URL as well.

```
bot-rollback: dry run; the config is /Users/.../mac-ops/config/bot-rollback.json
Bot 1, the paper-live trader (bot1)
  repository:            /Users/.../strategy-replay-workbench
  live ref:              origin/paper-live = 2254f0ab4ec692dd27134dc5d6d9d2d4b377c50a
  recorded rollback SHA: a2785675aba5d8bf3451e5893b5b46fe100b1679
  step fetch live ref: git -C /Users/.../strategy-replay-workbench fetch -q origin +refs/heads/paper-live:refs/remotes/origin/paper-live
  step precheck: git -C /Users/.../strategy-replay-workbench merge-base --is-ancestor a2785675... 2254f0ab...
  step rollback: node scripts/srw_promote_paper_live.cjs --break-glass-rollback a2785675...
  step health check: curl -fsS '$BOT1_HEALTH_URL/health'
```

A bot the command cannot resolve is reported with the reason: no live ref, no
recorded SHA, a SHA the checkout does not hold, a SHA that is not an ancestor
of the live commit, no rollback command, or no health check. The run exits
non-zero when any bot has a problem. A rollback to a guessed commit is worse
than no rollback.

## Executing

`--execute` runs, for each bot: a fetch of the live ref, the precheck, the
rollback commands and the health check. After the fetch it compares the live
ref with the commit the plan was made against. When the remote advanced in
between, nothing is rolled back and the run stops, so the command never rolls
back a promotion it did not inspect. A bot with an unresolved problem is
skipped and the run exits non-zero; the other bots still run. A failed step
stops the run. This ticket does not run it: a live rollback is an owner
decision outside the scope of the command and its dry run.

## What this does not do

- The dry run writes nothing: it reads the config and the git history and
  prints the steps. `--execute` runs the promotion path's own rollback command,
  which fetches and pushes, and then the health check.
- It does not write the config.
- It does not change the promotion path's gates, the bot order paths or any
  guard, permission or sandbox.
- It does not read secrets, and it prints no health URL.

## Where Bot 2 stands

Bot 1's path is complete: its live commit is carried by `origin/paper-live`
and the promotion path's own script rolls it back. Bot 2's live commit is not
carried by a ref in the repository. The promotion path records it in the
Railway deployment history, so the config marks Bot 2 unresolved rather than
guessing a commit. The dry run prints every Bot 2 step it lacks as `not recorded`. Naming Bot 2's ref and its rollback command in
`config/bot-rollback.json` is the remaining work, and the command then prints
Bot 2's steps the way it prints Bot 1's.

## Files

- `scripts/bot_rollback.py` — the command.
- `config/bot-rollback.json` — the bots, their refs and their commands.
- `tests/test_bot_rollback.py` — the config contract, the dry run and the
  execute path.
