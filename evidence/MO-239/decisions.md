# MO-239 - The shift works the whole board in intake order

The day tick worked the board from two throwaway scripts in a temporary
folder (`/tmp/coordgate/sweep.sh` and `/tmp/coordgate/prloop.py`). The
sweep takes 2 minutes 45 seconds and the tick's command timeout is 120
seconds, so the sweep was cut off and the gate loop never ran. The tick
queued no gates, sent back no failed gate findings and left the free
slots empty.

This ticket gives the tick one owned command that returns the whole
board, in the order the night shift runner orders it, and makes the tick
work that list.

## What changed

1. `coordinator/overnight/overnight` gained the `board` command, beside the
   night shift runner's own intake:

   ```sh
   overnight board --json
   ```

   It returns every board ticket and every open pull request the
   coordinator may act on, in the order `overnight order` prints them (the
   same code, one order, one place), and every item carries the one
   action it needs now:

   - `start`: the ready ticket has no blockers, no live builder thread, is
     not queued and its labels are sound. The item carries the dry-run
     command and the real one.
   - `gate`: the open pull request head has no gate and the pull request
     names a board ticket. The item carries `coordq gate <repo>#<n>`.
   - `fix`: the gate of that head ended `VERDICT: FAIL` and the builder
     has not received the findings. The item carries the `coordq start
     --tool t3_thread_send` command with the gate's own report.
   - `none`: nothing to do now, with the reason.

   The command reads only. It writes no file and keeps no list: the board
   is the list.

2. `coordinator/bin/coordq` gained the `gate` subcommand, so the tick can
   queue the gate of one open pull request head:

   ```sh
   coordq gate shyamsivakumar/mac-ops#247
   ```

   It reuses the queue's own gate request (same brief, same model rule,
   same merge rule, same Ascend rule) and records the head in the queue's
   own `gatedHeads`, so a head is never gated twice. The queue's own
   `gatekeep` keeps its rules: it gates the pull requests whose builder
   check names their head. `coordq gate` is the tick's backstop for a head
   no gate looked at; it says so when the builder check does not name the
   head yet, because the gate reports the check as it is.

3. The tick prompt calls the new command. `coordinator/pi/bin/coord-tick`
   names `overnight board --json` in its prompt, and the coordinator
   runtime's `loop/tick.md` now runs that command instead of the two
   throwaway scripts (the old text is kept at
   `/tmp/mo239/tick.md.before` and the change is a live-machine change to
   `~/Code/coordinator/loop/tick.md`, not a file this repository owns).

## Before and after

Before, from the tick's own log (`~/Library/Logs/coordinator/tick.log`,
today):

| tick | what happened |
| --- | --- |
| 15:18 PT | "The board sweep started 4 threads (live 4, queued 0, cap 6) before it timed out at 180 s. I didn't run the PR gate loop (`prloop.py`), because the sweep timed out first." |
| 15:51 PT | "The board sweep (`/tmp/coordgate/sweep.sh start`) timed out after 120 s this tick ... I didn't run `prloop.py`." The queue showed 2 live threads and 0 queued. |
| 16:24 PT | The same alert. |

So the tick reached a window of the board: **4 items acted on, 0 gates
queued, 0 failed gate findings sent back**, and the free slots stayed
empty.

After, the real command on today's board:

```sh
$ time python3 coordinator/overnight/overnight board --json
```

```
real	0m18.940s
```

| | before (the sweep's window) | after (the board command) |
| --- | --- | --- |
| items returned | 4 items acted on before a 120 s timeout | **126 items** (95 tickets, 31 open pull requests) |
| board tickets seen | a window of the repos the sweep reached | **111** tickets over 15 repositories (8 dropped by the filter) |
| open pull requests | 0 | **31**, of which **18 have no gate** |
| gates queued | 0 | **3** heads the tick can gate |
| failed gate findings sent back | 0 | **6** builders |
| ready work the tick can start | 4 threads before the timeout | **94** tickets |
| time | 2 min 45 s, over the timeout | **18.9 s** |

The command returns more items than the current sweep's window (126
against 4) and returns every open pull request head with no gate (18 of
31 open pull requests).

## Proof of the command

`evidence/MO-239/board.json` is the whole output of the run above. The
items with a gate to queue:

```
mac-ops#247            gate=none   action=gate  coordq gate shyamsivakumar/mac-ops#247
cairn#73                gate=none   action=gate  coordq gate shyamsivakumar/cairn#73
cairn#70                gate=none   action=gate  coordq gate shyamsivakumar/cairn#70
```

and the items whose failed gate has to go back to its builder:

```
mac-ops#202                        gate=fail   action=fix
strategy-replay-workbench#987       gate=fail   action=fix
strategy-replay-workbench#965       gate=fail   action=fix
strategy-replay-workbench#999       gate=fail   action=fix
strategy-replay-workbench#974       gate=fail   action=fix
```

`overnight order --dry-run` still prints the same order it printed
before this change (same groups, same counts, same shift-log line), and
it now reads the board in 19 seconds instead of 51.

## Must not cause

- No change to merge, push, the slot cap or the Ascend rules. The gate
  request `coordq gate` builds is the queue's own request, byte for byte.
- No ticket starts that the ticket CLI would refuse today. The command
  proposes a ticket only when it has no blockers, no live builder thread,
  no queued start and sound labels, and the ticket CLI refuses the rest
  before it starts anything.
- The tick must not start the same ticket twice: the command marks the
  tickets a live builder owns and the tickets the queue already holds.
- The tick must not gate a pull request head twice: the command reads the
  queue's own `gatedHeads`, and `coordq gate` refuses a head the queue
  already recorded.
- No secret was read or written.

## Not done in this change

The proof run of the tick itself (`dev.coordinator.tick` with the new
command in place, showing its log line naming the items it acted on, the
gate it queued and the finding it sent back) is the next step. The
command, the queue subcommand and the tick prompt are in place and the
command's own output is proven above.
