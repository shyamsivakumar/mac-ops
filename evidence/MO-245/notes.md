# MO-245 evidence: the shift's cycle health checks

## The live cycle

`OVERNIGHT_ROOT=<root> python3 coordinator/overnight/overnight shift --dry-run`
on the Mac, with the live queue and the live board. The receipt is
`cycle-live.md`: it shows all four checks ran, and each one says what it
ran.

The live board was clean at that moment: the coordinator had just acted on
the board (2026-11-13 22:32 PT), so the tickets that were started again
and again are parked in `loop/decisions.md` and the check skips a ticket
the log holds an open item for.

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
