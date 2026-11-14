# MO-209 · Overnight T3b: Intake filters Ascend, holds and needs-Shyam

Run id: `ticket:shyamsivakumar/mac-ops#177:a1`
Part: T3b of the overnight runner spec (spec issue #172, revision 2).
Refs #177.

## What this part adds

One module, `coordinator/overnight/` in mac-ops, installed by the existing
installer (`install_coordinator.py`). It reads GitHub, the ticket CLI and
the coordinator's decisions log, and it keeps no queue of its own.

Two commands, both read only:

| Command | What it does |
| --- | --- |
| `overnight filter --dry-run` | Filters the board and prints every drop with its reason. |
| `overnight check-pr --repo <repo> --number <n>` | The second check: refuses any Ascend pull request. |

The intake command from T3a (`overnight intake --dry-run`) is unchanged.

## The rules, and where each comes from

| Drop | Rule | Source |
| --- | --- | --- |
| Ascend work | A key from the spec's list (AUH, MCP, OPS, DBT, OMN), or a repository the merge gate refuses: the gate's repository rule (`repo.split('/')[0] != "shyamsivakumar"` plus the Ascend repository names) in `coordinator/bin/coordq`. | Spec section 5.1; the existing gate rule. |
| A repository off the allow list | The allow list is the board config, `coordinator/config/tickets.json`, the same list intake uses. | T3a. |
| A ticket marked `hold` | The word `HOLD` at the start of a line of the ticket's own text. | Spec section 7, drop list. |
| A ticket marked `needs Shyam` | The phrase `needs Shyam` at the start of a line or of a clause. | Spec section 7, drop list. |
| A ticket marked `design needed` | The phrase `design needed` at the start of a line or of a clause. | Spec section 7, drop list. |
| An open question in `loop/decisions.md` | The last line of the log that is about the ticket holds or parks it, or asks a question that was never answered. | Spec section 7, drop list. |

Two decisions worth naming:

- **A mark is the marked form, at the start of a line or of a clause.**
  The board uses "hold" as an ordinary word ("win, loss and hold counts",
  "the hold-out set"), and a search for the word alone drops real
  tickets. "HOLD" in capitals is the mark; "needs Shyam's OK" is a note,
  not a mark; and a brief that lists the marks themselves ("drop tickets
  marked hold, needs Shyam, design needed") is not marked either.
- **The decisions log is append-only history, so the last line about a
  ticket decides.** A hold outlives the question it was asked in, and a
  line that answers the question closes it. A ticket named in passing
  ("once SRW-1067 merges") is not the subject of the line, so it is not
  dropped by it.

## Proof

The commands are the real ones. Nothing was mocked in the first run.

### 1. The real board, today

```sh
python3 coordinator/overnight/overnight filter --dry-run
```

```
Overnight filter - dry run (read only)
Board: 112 tickets
Allowed repositories: 15
Decisions log: /Users/shyamsivakumar/Code/coordinator/loop/decisions.md

Kept: 104
Dropped: 8
Board repositories outside the allow list: 0

Drops (each with its reason)
  DROP shyamsivakumar/strategy-replay-workbench#917 SRW-1068 - hold in the decisions log: - 2026-11-12T22:45Z PARKED (needs Shyam): SRW-1068 #917 (last SRW-1033 build slice) replaces refusal-until-false ex...
  DROP shyamsivakumar/strategy-replay-workbench#468 SRW-685 - hold in the decisions log: - 2026-11-12T22:06Z ANSWERED (Shyam via his coding bot, 2:06 PM PT): HOLD SRW-685. Do not merge PR #895 (remove unuse...
  DROP digitized/Concerning#32 NING-1 - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#37 NING-2 - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#38 NING-3 - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#39 NING-4 - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#40 NING-5 - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#46 NING-6 - Ascend repo: digitized/Concerning is not a shyamsivakumar repository

Ascend items kept: 0
```

Zero Ascend items survive. Every drop prints its reason.

No ticket on today's board carries a body mark, so no drop comes from
the body rules today. The rules below prove they fire.

### 2. The rules on a fixture board

The fixture is in `evidence/MO-209/fixtures/`: a stand-in for the ticket
CLI, a stand-in for `gh issue list` and `gh pr view`, and a decisions log
that writes its open items the way the real log does. The real commands
run against them.

```sh
OVERNIGHT_TICKET=$PWD/evidence/MO-209/fixtures/fake_ticket.py \
OVERNIGHT_GH=$PWD/evidence/MO-209/fixtures/fake_gh.py \
OVERNIGHT_DECISIONS=$PWD/evidence/MO-209/fixtures/decisions.md \
python3 coordinator/overnight/overnight filter --dry-run
```

```
Overnight filter - dry run (read only)
Board: 11 tickets
Allowed repositories: 15
Decisions log: .../evidence/MO-209/fixtures/decisions.md

Kept: 1
Dropped: 10
Board repositories outside the allow list: 2

Drops (each with its reason)
  DROP shyamsivakumar/mac-ops#901 MO-901 - marked hold: HOLD: wait for the census chain.
  DROP shyamsivakumar/mac-ops#902 MO-902 - marked needs Shyam: Nothing to add. Needs Shyam: pick one of the two.
  DROP shyamsivakumar/mac-ops#903 MO-903 - marked design needed: design needed before any code is written.
  DROP shyamsivakumar/mac-ops#904 AUH-1 - Ascend key AUH
  DROP slash-eureka/dbt#905 DBT-9 - Ascend key DBT
  DROP shyamsivakumar/not-on-the-list#906 NTL-1 - repo not on the allow list: shyamsivakumar/not-on-the-list
  DROP shyamsivakumar/mac-ops#907 MO-907 - open item in the decisions log: - 2026-11-13T00:00Z PARKED (needs Shyam): MO-907 #907 (a ticket with a parked question) waits for Shyam's answer. Rec...
  DROP shyamsivakumar/mac-ops#908 MO-908 - open item in the decisions log: - 2026-11-13T00:10Z OPEN (needs answer): MO-908 #908 (a ticket with an OPEN question) - waive it or send it to the bu...
  DROP shyamsivakumar/mac-ops#909 MO-909 - open question in the decisions log: - 2026-11-13T00:20Z Q: MO-909 #909 (a ticket with a Q: question) which option?
  DROP shyamsivakumar/mac-ops#910 MO-910 - open question in the decisions log: - 2026-11-13T00:30Z asked Shyam about MO-910 #910 (a ticket Shyam was asked about), waiting.

Ascend items kept: 0
```

### 3. The filter fails closed

A read that fails ends in a non-zero exit, and nothing it could not check
is kept.

The ticket text cannot be read (`gh issue list` fails):

```sh
OVERNIGHT_TICKET=$PWD/evidence/MO-209/fixtures/fake_ticket.py \
OVERNIGHT_GH=/usr/bin/false \
OVERNIGHT_DECISIONS=$PWD/evidence/MO-209/fixtures/decisions.md \
python3 coordinator/overnight/overnight filter --dry-run
```

```
REFUSED: the ticket text of these repositories could not be read: shyamsivakumar/mac-ops, ...

Kept: 0
Dropped: 8
  DROP shyamsivakumar/mac-ops#900 MO-900 - unverified: the ticket text could not be read
  ...
  DROP shyamsivakumar/mac-ops#907 MO-907 - hold in the decisions log: - 2026-11-13T00:00Z PARKED (needs Shyam): MO-907 #907 ...

Ascend items kept: 0
REFUSED: the filter cannot return a list it could not fully check.
```

exit code 1. The decisions-log check still ran on the ticket whose text
could not be read, because that check does not use the ticket text.

The decisions log is missing:

```sh
OVERNIGHT_DECISIONS=/nonexistent/decisions.md \
python3 coordinator/overnight/overnight filter --dry-run
```

```
REFUSED: the decisions log /nonexistent/decisions.md could not be read

Kept: 0
Dropped: 8
  DROP shyamsivakumar/mac-ops#900 MO-900 - unverified: the decisions log could not be read
  ...
REFUSED: the filter cannot return a list it could not fully check.
```

exit code 1. A stale board is refused the same way, before any list is
printed.

### 4. The second check refuses an Ascend pull request

An Ascend repository:

```sh
python3 coordinator/overnight/overnight check-pr --repo slash-eureka/dbt --number 1
```

```
REFUSED: slash-eureka/dbt#1: Ascend repo: slash-eureka/dbt is not a shyamsivakumar repository
```

exit code 1.

A pull request in a personal repository whose branch carries an Ascend
key, hidden behind an earlier key-like token:

```sh
OVERNIGHT_GH=$PWD/evidence/MO-209/fixtures/fake_gh.py \
python3 coordinator/overnight/overnight check-pr --repo shyamsivakumar/mac-ops --number 1
```

```
REFUSED: shyamsivakumar/mac-ops#1: Ascend key AUH-3
  branch t3/fix-12-auh-3
```

exit code 1. Every key in the branch is read, not only the first.

A pull request the check cannot read is refused, not passed:

```sh
OVERNIGHT_GH=/usr/bin/false \
python3 coordinator/overnight/overnight check-pr --repo shyamsivakumar/mac-ops --number 1
```

```
REFUSED: shyamsivakumar/mac-ops#1: the pull request could not be read, so the check cannot be trusted.
```

exit code 1.

## What the two review rounds changed

Two Opus review rounds read `git diff origin/main...HEAD` and both
returned `VERDICT: FAIL`. What the rounds found, and what this branch
now does with it:

| Finding | Now |
| --- | --- |
| The marks matched prose and briefs | A mark is the marked form: `HOLD` in capitals, `Needs Shyam:` with its question, `design needed` with what it waits for. "needs Shyam's OK" and "hold counts" are not marks, and a brief that lists the marks is not marked. |
| The filter failed open when a read failed | It fails closed. An unreadable repository, a missing decisions log and a stale board all end in a non-zero exit, and every ticket it could not check is dropped as unverified instead of kept. The decisions-log check runs whether or not the ticket text could be read. |
| `check-pr` failed open when the pull request could not be read | It refuses the pull request and exits non-zero. It never prints `OK` for a pull request it did not read. |
| The decisions-log rule missed `OPEN`, `Q:` and a line ending in `?` | It reads `HOLD`, `HELD`, `PARK`, `PARKED`, `OPEN`, `Q:`, "needs Shyam", "asked Shyam about", a line that ends in a question mark and the log's own `(Recommended:` marker. A line is about a ticket when it names the ticket with its issue number in either order, or names it right after the line's verb, so a bare `#number` no longer drops a ticket in another repository. |
| The gate's per-repository `ascend` flag was not read | It is read now, from the same board config the gate reads. |
| `check-pr` read only the first key in the branch name | Every key in the branch and in the pull request body is read, so `t3/fix-12-auh-3` still shows its Ascend key. |
| The open issue list was capped at 500 with no warning | A repository whose list reaches the limit is treated as unread, so the filter refuses. |

One thing stays out of scope: the tick also writes questions for Shyam to
`decisions.json`, and this part reads `loop/decisions.md` only, as the
brief names it. The next part can read both.

## Open point for Shyam

`digitized/Concerning` (key NING) is in the board config, so the
coordinator works on it, but the merge gate's own Ascend rule refuses any
repository that `shyamsivakumar` does not own, and the gate therefore
stops at the verdict for that repository's pull requests. The shift
follows the gate's rule and leaves that work alone, because a pull
request it cannot merge is a night wasted. If NING should be worked on
overnight, the gate rule needs to name the Ascend repositories instead of
the owner, and that is a change to the merge path, not to this part.
