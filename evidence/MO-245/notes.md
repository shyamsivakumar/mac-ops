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

## The injected-input proof

The checks take their data as an argument, so the repo's own proof
harness can drive them without touching the machine. The new
`cycle-health` eval lives in `coordinator/overnight/selftest.py`, next to
the watchdog and drift evals that already prove the cycle's health
boundary:

    PYTHONPATH=coordinator/bin python3 coordinator/overnight/selftest.py

The eval starts no process, opens no socket and reads no board: it hands
the checks the probes, the log tails, the install status, the ticket
records and the issue states, and it proves the four checks find their
breaks and that a read which failed is never a clean result. The output
is `selftest.txt`; every eval in the file passes.

## The cut-off pull request list

`gh pr list` returns at most 100 pull requests of a repository, so a
list that stops at the limit is missing the ones past it. The check
must not classify a ticket from such a list, because a ticket whose
pull request is past the limit would look like it has none.

The proof is `cut-list.md`: it hands the check the inputs twice, once
with a pull request list that was cut off and once with a whole one.
The first run classifies no ticket and says the list was cut off; the
second run classifies the ticket and reports it. The live cycle on this
head is `cycle-live-cut.md`: all four checks ran against the live queue
and the live board.

## The unreadable log

A queue log that cannot be read is not a log without a traceback and
not a log without a refusal. The read says it failed, and the check
that needed the log is incomplete: the receipt says the log could not
be read, for the crash check and for the text blocker check.

The proof is a cycle whose queue folder holds no log at all:

    COORDQ_DIR=<empty folder> OVERNIGHT_ROOT=<root> \
    python3 coordinator/overnight/overnight shift --dry-run

The receipt is `cycle-unreadable-log.md`. It shows the two queue logs
reported as "could not be read", the tools check and the blockers check
each reporting an incomplete check, and no finding claimed from a log
nobody could read. The `cycle-health` eval holds the same cases.

## The stale board

The ticket CLI owns the board's cache. When it cannot reach GitHub it
falls back to that cache and says the list is stale. A stale list is
not a list with no tickets: the board could not be refreshed, so the
tickets it names are not known, and the check that reads the board is
incomplete rather than clean.

The proof is a cycle whose ticket CLI is a stub that returns a stale
board with no tickets:

    OVERNIGHT_TICKET=<stub> OVERNIGHT_ROOT=<root> \
    python3 coordinator/overnight/overnight shift --dry-run

The receipt is `cycle-stale-board.md`. The attempts check says "the
board list is stale, so no ticket was classified" and reports an
incomplete check, instead of the clean "no finding" an empty stale
board used to produce. The `cycle-health` eval holds the same case.

## The cut-off issue comments

GitHub returns the first 100 comments of an issue with the issue in a
list read. The starts past that limit are not known, so a ticket whose
start comments sit beyond it cannot be counted, and a ticket started
three or more times would slip past the check. The check now reports
the cut-off as an incomplete check and does not classify that ticket.

The proof is a cycle whose `gh` is a stub that pads the first issue of
each repository past the 100-comment limit:

    OVERNIGHT_GH=<stub> OVERNIGHT_ROOT=<root> \
    python3 coordinator/overnight/overnight shift --dry-run

The receipt is `cycle-cut-comments.md`. It shows one incomplete-check
finding per repository ("the issue's comments were cut off at 100, so
the number of starts is not known and the ticket is not classified") and
no ticket counted from a list that is not whole. The `cycle-health`
eval holds the same case.
