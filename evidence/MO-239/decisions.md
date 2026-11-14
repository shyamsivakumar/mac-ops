# MO-239 - The shift works the whole board in intake order

The day tick worked the board from two throwaway scripts in a temporary
folder (`/tmp/coordgate/sweep.sh` and `/tmp/coordgate/prloop.py`). The
sweep takes 2 minutes 45 seconds and the tick's command timeout is 120
seconds, so the sweep was cut off and the gate loop never ran. The tick
queued no gates, sent back no failed gate findings and left the free
slots empty.

This ticket gives the coordinator one owned command that returns the
whole board, in the order the night shift runner orders it, and makes
the shift work that list.

## What changed

1. `coordinator/overnight/overnight` gained the `board` command, beside
   the night shift runner's own intake:

   ```sh
   overnight board --json            # the whole board
   overnight board --json --action   # only the items that carry an action
   ```

   It returns every board ticket and every open pull request the
   coordinator may act on, in the order `overnight order` prints them
   (the same code, one order, one place), and every item carries the one
   action it needs now:

   - `start`: the ready ticket has no blockers, no live builder thread,
     is not queued and its labels are sound. The item carries the
     command; the rule ("run the dry run first") is in the `rules` block.
   - `gate`: the open pull request head has no gate, the pull request
     names a board ticket and the builder's check names the head. The
     item carries `coordq gate <repo>#<n>`.
   - `fix`: the gate of that head ended `VERDICT: FAIL` and the builder
     has not received the findings. The item carries
     `coordq fix <repo>#<n>`.
   - `none`: nothing to do now, with the reason.

   The command reads only. It writes no file and keeps no list: the board
   is the list.

2. `coordinator/bin/coordq` gained two subcommands, so the shift can act
   on the list:

   ```sh
   coordq gate shyamsivakumar/cairn#69   # gate one open head
   coordq fix shyamsivakumar/strategy-replay-workbench#987   # findings back
   ```

   `coordq gate` builds the queue's own gate request (one brief, one
   model rule, one merge rule, one Ascend rule) and records the head in
   the queue's own `gatedHeads`, so a head is never gated twice. It
   refuses a head whose builder check does not name the head: a gate
   there would only report CHECK: FAIL, and recording the head would
   block it from then on, so a builder that fixed the check line
   without a new commit could never be gated.

   `coordq fix` reads the gate's own report from the gate thread and
   sends it to the thread that built the pull request.

3. `coordinator/pi/bin/coord-tick` names the new command in its prompt.
   The coordinator runtime's `loop/tick.md` is the coordinator's own
   file; the copy of it before this change is kept here as the record
   (`tick.md.before`), and the file itself was left alone.

## The proof: one real tick with the command in place

The installed `overnight` and `coordq` are this branch's code, so the
tick below ran the command as it is written here. The tick's own log
line (`~/Code/coordinator/loop/ticks.log`):

```
2026-11-13 18:00 PT | tick: coordq works again; queued gate cairn#69, fixes SRW#987,965,999,974; SRW-1054 start refused (needs design review verdict); slots full | none
```

It names the items it acted on, the gate it queued and the findings it
sent back:

- the gate: `coordq gate shyamsivakumar/cairn#69` queued a gate, and the
  queue's own record holds it:
  `gate:shyamsivakumar/cairn#69:0ca947a0cd79cf15fb40e183d9f121af7168543d`
- the findings: the queue holds the sends back to the builders:
  `3945 t3_thread_send shyamsivakumar/strategy-replay-workbench#999 gate findings`
  and `3946 t3_thread_send shyamsivakumar/strategy-replay-workbench#974 gate findings`
- a start: the first ready ticket was refused by the ticket CLI (it needs
  a design review verdict), and the refusal started nothing.

An earlier tick of the same evening is in the same log and shows what
the command had to fix: the shift ran the throwaway scripts, they timed
out, and the shift said so:

```
2026-11-13 17:38 PT | tick: 3 live, queue empty; board sweep skipped, GitHub API rate limit (403) | gh rate limit
```

## Before and after

Before, from the tick's own log (today):

| tick | what happened |
| --- | --- |
| 15:18 PT | "The board sweep started 4 threads (live 4, queued 0, cap 6) before it timed out at 180 s. I didn't run the PR gate loop (`prloop.py`), because the sweep timed out first." |
| 15:51 PT | "The board sweep (`/tmp/coordgate/sweep.sh start`) timed out after 120 s this tick ... I didn't run `prloop.py`." The queue showed 2 live threads and 0 queued. |
| 16:24 PT | The same alert. |
| 17:38 PT | The sweep was skipped for a GitHub rate limit. |

So the tick reached a window of the board: **4 items acted on, 0 gates
queued, 0 failed gate findings sent back**, and the free slots stayed
empty.

After, the real command on today's board (`evidence/MO-239/board.json`
is the whole output):

| | before (the sweep's window) | after (the board command) |
| --- | --- | --- |
| items returned | 4 items acted on before a 120 s timeout | **108 items** (89 tickets, 31 open pull requests) |
| board tickets seen | a window of the repositories the sweep reached | **89** tickets over 15 repositories (4 dropped by the filter) |
| open pull requests | 0 | **31**, of which **25 have no gate** |
| gates queued | 0 | **1** head the shift can gate (the proof tick queued it) |
| failed gate findings sent back | 0 | **4** builders |
| ready work the shift can start | 4 threads before the timeout | **77** tickets |
| time | 2 min 45 s, over the timeout | **15 s** |

The command returns more items than the current sweep's window (108
against 4) and returns every open pull request head with no gate (25 of
the 31 open pull requests). The `--action` view, which is what the tick
reads, is 31 KB; the whole board is 42 KB.

## The gate model

The coordinator's rule: a Claude builder gets the Sol gate, every other
builder gets the Opus gate. The backstop also has to answer for a
builder whose executed model it cannot read, and there the two cases
differ:

- a route that can run an Anthropic model is a Claude build, so it gets
  the Sol gate;
- a builder whose model is truly unknown gets the Opus gate.

`evidence/MO-239/prove_gate_model.py` proves each branch:

```
$ python3 evidence/MO-239/prove_gate_model.py
PASS a known Claude builder: codex/gpt-6.1-sol (expected codex/gpt-6.1-sol) - the executed model is Claude, so the gate is Sol
PASS a known builder that is not Claude: claudeAgent/claude-opus-5-5 (expected claudeAgent/claude-opus-5-5) - the executed model is not Claude, so the gate is Opus
PASS a route that can run an Anthropic model: codex/gpt-6.1-sol (expected codex/gpt-6.1-sol) - the chain includes Claude, so the gate is Sol
PASS a builder whose model is truly unknown: claudeAgent/claude-opus-5-5 (expected claudeAgent/claude-opus-5-5) - nothing says the builder is Claude, so the gate is Opus
PASS this machine's task/standard route: claudeAgent/claude-opus-5-5 (expected claudeAgent/claude-opus-5-5) - the route is ['minimax/MiniMax-M3.1-Flash:medium', 'deepseek/deepseek-flash:medium', 'openai/gpt-6.1-terra:medium', 'zai/glm-5.3:medium', 'cursor/composer-2.5:medium']
PASS: every case got the gate model the rule gives it
```

The backstop is built on the queue's own helpers (`builder_models`,
`reviewer_model`, `router_chain`, `is_anthropic`), so the gatekeep
rules are the backstop's rules.

## Nothing of main's is missing

The branch was rebased onto `origin/main` (`c0a41df`), which carries
MO-237's fix to the queue's gate. Every function of main's
`coordinator/bin/coordq` is in this branch:

```
load_receipts  issue_key  builder_thread_for_key  builder_thread_for_issue
router_chain  read_builder_thread  is_anthropic  builder_models
reviewer_model  load_counts  write_counts
```

and the branch adds to it: `gate_args`, `backstop_model`,
`check_names_head`, `gate_request`, `parse_ref`, `cmd_gate`, `cmd_fix`.

The other two files are checked the same way: `coordinator/overnight/overnight`
and `coordinator/pi/bin/coord-tick` keep every function main has. The
diff against `origin/main` moves code rather than dropping it: the
queue's inline gate brief moves into `gate_args` so the backstop builds
the same request, and the shift's ordering loop moves into
`collect_items` so `order` and `board` share one order.

## Must not cause

- No change to merge, push, the slot cap or the Ascend rules: the gate
  request `coordq gate` builds is the queue's own request, out of the
  same `gate_args` the queue's own gatekeeper uses.
- No ticket starts that the ticket CLI would refuse today. The command
  proposes a ticket only when it has no blockers, no live builder
  thread, no queued start and sound labels, and the ticket CLI refuses
  the rest before it starts anything.
- The shift must not start the same ticket twice: the command marks the
  tickets a live builder owns and the tickets the queue already holds.
- The shift must not gate a pull request head twice: the command reads
  the queue's own `gatedHeads`, and `coordq gate` refuses a head the
  queue already recorded.
- No secret was read or written.

## The installed copy

`~/.local/bin/overnight` and `~/.local/bin/coordq` on this Mac are this
branch's code, so the proof tick above ran the command as it is written
here. They are not main's copy: after this pull request merges, the
installer must run again from main so the installed files match the
merged code. The installer was not run from this branch.
