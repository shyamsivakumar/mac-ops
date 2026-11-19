# One-command rollback for Bot 1 and Bot 2

`scripts/bot_rollback.py` rolls each bot back to the rollback SHA that the
promotion path recorded for it, and then checks that the bot is healthy. The
dry run is the default: it prints the exact steps for every bot and changes
nothing.

```sh
python3 scripts/bot_rollback.py --dry-run
python3 scripts/bot_rollback.py --dry-run --bot bot1
python3 scripts/bot_rollback.py --execute --bot bot1
```

## What the command reads

The promotion path records what it moved each bot from. That record is the
rollback ledger, one JSON file with one entry per bot. The command reads the
ledger and never writes it.

The default ledger path is `.git/srw-deploy-receipts/rollback.json` inside the
repository the bots live in, next to the deploy receipts the promotion path
already writes. `--ledger` points at another file, and `--srw-repo` at another
repository.

Ledger schema, version 1:

```json
{
  "schemaVersion": 1,
  "bots": [
    {
      "id": "bot1",
      "label": "Bot 1, the paper-live trader",
      "rollbackSha": "1f0d1a3a805efa235acc383ba768c7e317313bd3",
      "liveRef": "origin/paper-live",
      "rollbackCommand": ["node", "scripts/srw_promote_paper_live.cjs",
                          "--break-glass-rollback"],
      "healthCommand": ["node", "scripts/srw_trader_health.cjs"]
    },
    {
      "id": "bot2",
      "label": "Bot 2",
      "rollbackSha": "f8cb4d92c677c5c67ba0e160859fab19165d1785",
      "liveRef": "origin/bot2-live",
      "rollbackCommand": ["node", "scripts/srw_promote_bot2.cjs",
                          "--break-glass-rollback"],
      "healthCommand": ["node", "scripts/srw_bot2_health.cjs"]
    }
  ]
}
```

- `rollbackSha` is the commit the promotion path moved the bot from. It must be
  a 40 character commit SHA.
- `liveRef` is the ref that carries the live commit. When it is present, the
  dry run resolves it and adds the ancestor precheck as the first step.
- `rollbackCommand` is the promotion path's own command without the SHA; the
  command appends the recorded SHA. The promotion path keeps its own gates.
- `healthCommand` is the check that says the bot is healthy after the rollback.

Both commands run in the repository the ledger belongs to, so relative paths
in them resolve there.

## What the dry run prints

For each bot: the recorded rollback SHA, the commit the live ref points at,
and one line per step with the exact command.

```
bot-rollback: dry run; the ledger is /Users/.../strategy-replay-workbench/.git/srw-deploy-receipts/rollback.json
Bot 1, the paper-live trader (bot1)
  recorded rollback SHA: 1f0d1a3a805efa235acc383ba768c7e317313bd3
  current live commit:   origin/paper-live = 03a10b9c...
  step precheck: git -C /Users/.../strategy-replay-workbench merge-base --is-ancestor 1f0d1a3a... 03a10b9c...
  step rollback: node scripts/srw_promote_paper_live.cjs --break-glass-rollback 1f0d1a3a...
  step health check: node scripts/srw_trader_health.cjs
```

The dry run also notes when the recorded SHA is not an ancestor of the live
commit, and when the checkout does not hold the recorded commit at all.

## Executing

`--execute` runs the rollback command and then the health check for each bot,
in that order, and stops at the first bot whose rollback fails. The exit code
is 1 when a bot fails. This ticket does not run it: a live rollback is an
owner decision outside the scope of the command and its dry run.

## What this does not do

- It does not write the ledger. The promotion path records the rollback SHA.
- It does not change the promotion path's gates, the bot order paths or any
  live service.
- It does not read secrets.

## Files

- `scripts/bot_rollback.py` — the command.
- `tests/test_bot_rollback.py` — the ledger contract and the dry run.
