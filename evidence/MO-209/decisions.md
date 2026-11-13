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
| Ascend work | A key from the spec's list (AUH, MCP, OPS, DBT, OMN), or a repository the merge gate refuses. The repository rule is the one in `coordinator/bin/coordq` (`repo.split('/')[0] != "shyamsivakumar"` plus the Ascend repository names), so the shift and the gate never disagree about what Ascend is. | Spec section 5.1; the existing gate rule. |
| A repository off the allow list | The allow list is the board config, `coordinator/config/tickets.json`, the same list intake uses. | T3a. |
| A ticket marked `hold` | The word `HOLD` at the start of a line of the ticket's own text. | Spec section 7, drop list. |
| A ticket marked `needs Shyam` | The phrase `needs Shyam` at the start of a line or of a clause. | Spec section 7, drop list. |
| A ticket marked `design needed` | The phrase `design needed` at the start of a line or of a clause. | Spec section 7, drop list. |
| An open question in `loop/decisions.md` | The last line of the log that is about the ticket holds or parks it, or asks a question that was never answered. | Spec section 7, drop list. |

Two decisions worth naming:

- **A mark stands at the start of a line or of a clause.** The board uses
  "hold" as an ordinary word ("win, loss and hold counts", "a hold
  outcome"), and a search for the word alone drops real tickets. The same
  is true of "needs Shyam's OK", which is a note, not a mark.
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
Board: 121 tickets
Allowed repositories: 15
Decisions log: /Users/shyamsivakumar/Code/coordinator/loop/decisions.md

Kept: 113
Dropped: 8
Board repositories outside the allow list: 0

Drops (each with its reason)
  DROP shyamsivakumar/strategy-replay-workbench#917 SRW-1068 - hold in the decisions log: - 2026-11-12T22:45Z PARKED (needs Shyam): SRW-1068 #917 (last SRW-1033 build slice) replaces refusal-until-false ex...
  DROP shyamsivakumar/strategy-replay-workbench#468 SRW-685 - hold in the decisions log: - 2026-11-12T22:06Z ANSWERED (Shyam via his coding bot, 2:06 PM PT): HOLD SRW-685. Do not merge PR #895 (remove unuse...
  DROP digitized/Concerning#32 - - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#37 - - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#38 - - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#40 - - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#46 - - Ascend repo: digitized/Concerning is not a shyamsivakumar repository
  DROP digitized/Concerning#39 - - Ascend repo: digitized/Concerning is not a shyamsivakumar repository

Ascend items kept: 0
```

Zero Ascend items survive. Every drop prints its reason.

No ticket on today's board carries a body mark, so no drop comes from
the body rules today. The rules below prove they fire.

### 2. The rules on a fixture board

The fixture is in `evidence/MO-209/fixtures/`: a stand-in for the ticket
CLI, a stand-in for `gh issue list`, and a decisions log. The real
command runs against them.

```sh
OVERNIGHT_TICKET=$PWD/evidence/MO-209/fixtures/fake_ticket.py \
OVERNIGHT_GH=$PWD/evidence/MO-209/fixtures/fake_gh.py \
OVERNIGHT_DECISIONS=$PWD/evidence/MO-209/fixtures/decisions.md \
python3 coordinator/overnight/overnight filter --dry-run
```

```
Overnight filter - dry run (read only)
Board: 8 tickets
Allowed repositories: 15
Decisions log: .../evidence/MO-209/fixtures/decisions.md

Kept: 1
Dropped: 7
Board repositories outside the allow list: 2

Drops (each with its reason)
  DROP shyamsivakumar/mac-ops#901 MO-901 - marked hold: HOLD: wait for the census chain.
  DROP shyamsivakumar/mac-ops#902 MO-902 - marked needs Shyam: Nothing to add. Needs Shyam: pick one of the two.
  DROP shyamsivakumar/mac-ops#903 MO-903 - marked design needed: design needed before any code is written.
  DROP shyamsivakumar/mac-ops#904 AUH-1 - Ascend key AUH
  DROP slash-eureka/dbt#905 DBT-9 - Ascend key DBT
  DROP shyamsivakumar/not-on-the-list#906 NTL-1 - repo not on the allow list: shyamsivakumar/not-on-the-list
  DROP shyamsivakumar/mac-ops#907 MO-907 - hold in the decisions log: - 2026-11-13T00:00Z PARKED (needs Shyam): MO-907 #907 (a ticket with an open question) waits for Shyam's answer. Reco...

Ascend items kept: 0
```

### 3. The second check refuses an Ascend pull request

```sh
python3 coordinator/overnight/overnight check-pr --repo slash-eureka/dbt --number 1
```

```
REFUSED: slash-eureka/dbt#1: Ascend repo: slash-eureka/dbt is not a shyamsivakumar repository
```

The command exits 1 on a refusal. A pull request in a personal repository
whose branch carries an Ascend key (`auh-12-fix`) is refused on the key.

## Checks

- `python3 scripts/mac_ops_fast_check.py`: passed.
- Full local check, through `~/.local/bin/heavy`:
  `python3 -m unittest discover -s tests -t .` → 148 tests, OK.
- No new test files. The proof above is the real command on the real
  board and on a fixture board.

## Must not cause

Nothing here merges, pushes, raises the slot cap or changes the Ascend
rules. The filter reads; `check-pr` refuses. The board config, the ticket
CLI, `coordq` and the gate are untouched.

## Open point for Shyam

`digitized/Concerning` (key NING) is in the board config, so the
coordinator works on it, but the merge gate's own Ascend rule refuses any
repository that `shyamsivakumar` does not own, and the gate therefore
stops at the verdict for that repository's pull requests. The shift
follows the gate's rule and leaves that work alone, because a pull
request it cannot merge is a night wasted. If NING should be worked on
overnight, the gate rule needs to name the Ascend repositories instead of
the owner, and that is a change to the merge path, not to this part.
