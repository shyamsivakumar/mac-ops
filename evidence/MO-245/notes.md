# MO-245 evidence: the shift's cycle health checks

## The live cycle

    OVERNIGHT_ROOT=<root> python3 coordinator/overnight/overnight shift --dry-run

on the Mac, with the live queue and the live board. The receipt is
`cycle-live.md`: it shows all four checks ran and each one says what it
ran. That run found five real breaks:

- the installed coordinator differs from the merged main
  (`~/.local/bin/coordq`, `~/.local/bin/ticket`,
  `~/.coordinator/AGENT-RULES.md`, `~/.local/bin/selftest.py`), so the
  live Mac runs code that is not main;
- four board tickets were started nine or more times and have no open
  pull request (`NING-1`, `CTL-25`, `CTL-26`, `FBT-33`), so their briefs
  are broken.

## The fixture cycle

The same command with the queue, the install checkout and the decisions
log pointed at fixtures:

    COORDQ_DIR=<fixture>/queue \
    OVERNIGHT_ROOT=<fixture>/root \
    OVERNIGHT_DECISIONS=<fixture>/empty-decisions.md \
    MAC_OPS_DIR=<fixture>/mac-ops \
    python3 coordinator/overnight/overnight shift --dry-run

The receipt is `cycle-fixture.md`, and it shows each check finding its
break:

- the tools: `coordq status` fails under the launchd interpreter, because
  the fixture queue holds no `config.json`;
- the installed files: the fixture status says `in_sync: false` and names
  the file that differs;
- the board's attempts: four real board tickets were started four or more
  times and have no open pull request (`SRW-984`, `SRW-968`, `SRW-988`,
  `SRW-791`). With the live decisions log they are skipped, because the
  log parks them;
- the board's blockers: the refusal of `strategy-replay-workbench#807`
  names `SRW-963 (#680)`, and `#680` is closed, so the text blocker is
  false.

## The incomplete-check cycle

The same command with a `gh` stub that fails the two reads it must not
guess at (`pr list` and `api`), and a queue that holds one refusal
naming a closed issue:

    OVERNIGHT_GH=<stub> COORDQ_DIR=<fixture>/queue \
    OVERNIGHT_ROOT=<fixture>/root \
    python3 coordinator/overnight/overnight shift --dry-run

The receipt is `cycle-incomplete.md`, and it shows the two rules:

- a pull request list that could not be read means the tickets of that
  repository are not classified at all: the receipt says the list could
  not be read, and no ticket is reported as having no open pull request;
- an issue whose state could not be read means the text blocker check is
  incomplete for it: the receipt says so instead of reporting that the
  blocker is not false.
