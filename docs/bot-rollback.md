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
carries the bot's live commit. The ref keeps its own history, so the commit
before the last one is the commit the promotion path moved the bot from. That
is the recorded rollback SHA, and the command reads it from the ref's history.

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
      "healthPath": "/health"
    }
  ]
}
```

- `repository` is the checkout the bot lives in. The rollback and the health
  check run there, so a relative path in them resolves there.
- `liveRef` is the ref that carries the live commit.
- `rollbackSha` pins the rollback SHA. When it is null, the command reads the
  SHA from the ref's history.
- `rollbackCommands` are the commands that roll the bot back, in order. The
  token `{sha}` is where the recorded SHA goes; a command without the token
  gets the SHA as its last argument.
- `healthUrlEnv` names the environment variable that holds the base URL of the
  bot's health endpoint, and `healthPath` the path under it. The health check
  is `curl -fsS <url><path>`. A bot that is checked by a script instead
  names it in `healthCommand`.

## What the dry run prints

For each bot: the repository, the live ref and the commit it points at, the
recorded rollback SHA, and one line per step with the exact command.

```
bot-rollback: dry run; the config is /Users/.../mac-ops/config/bot-rollback.json
Bot 1, the paper-live trader (bot1)
  repository:            /Users/.../strategy-replay-workbench
  live ref:              origin/paper-live = 2254f0ab4ec692dd27134dc5d6d9d2d4b377c50a
  recorded rollback SHA: a2785675aba5d8bf3451e5893b5b46fe100b1679
  step precheck: git -C /Users/.../strategy-replay-workbench merge-base --is-ancestor a2785675... 2254f0ab...
  step rollback: node scripts/srw_promote_paper_live.cjs --break-glass-rollback a2785675...
  step health check: curl -fsS https://bot1.example/health
```

A bot the command cannot resolve is reported with the reason: no live ref, no
recorded SHA, a SHA the checkout does not hold, a SHA that is not an ancestor
of the live commit, no rollback command, or no health check. The run exits
non-zero when any bot has a problem. A rollback to a guessed commit is worse
than no rollback.

## Executing

`--execute` runs the rollback commands and then the health check for each bot,
in that order, and stops at the first failure. Nothing runs for a bot with an
unresolved problem, and no bot runs when any bot has one. This ticket does not
run it: a live rollback is an owner decision outside the scope of the command
and its dry run.

## What this does not do

- It does not write the config, the repository or any live service.
- It does not change the promotion path's gates, the bot order paths or any
  guard, permission or sandbox.
- It does not read secrets.

## Where Bot 2 stands

Bot 1's path is complete: its live commit is carried by `origin/paper-live`
and the promotion path's own script rolls it back. Bot 2's live commit is not
carried by a ref in the repository. The promotion path records it in the
Railway deployment history, so the config marks Bot 2 unresolved rather than
guessing a commit. Naming Bot 2's ref and its rollback command in
`config/bot-rollback.json` is the remaining work, and the command then prints
Bot 2's steps the way it prints Bot 1's.

## Files

- `scripts/bot_rollback.py` — the command.
- `config/bot-rollback.json` — the bots, their refs and their commands.
- `tests/test_bot_rollback.py` — the config contract, the dry run and the
  execute path.
