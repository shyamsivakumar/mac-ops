# Board "Needs you" accuracy (Refs #360)

The board's "Needs you" column showed failed and interrupted threads that
asked Shyam nothing. The column now holds only three things: a coordinator
decision from `~/Code/coordinator/decisions.json`, a thread with a pending
request, and a thread whose last assistant message ends with a question or a
`WAITING:` line. The word "waiting" alone does not count; the line needs the
colon. Failed and interrupted runs that ask nothing move to the
collapsed **Dead runs** column, which shows their count.

## What changed

- `coordinator/mods/cockpit/asks.js` is the classifier: `endsWithAsk` reads a
  turn's last line, `columnOf` decides the column for a group of threads, and
  `place` gives a real ask precedence over a mergeable PR. An asking thread in
  a group that is otherwise running still counts, because that turn is asking.
- `coordinator/mods/cockpit/hub.js` reads `decisions.json` as cards, and reads
  the tail of each finished thread once per change (cached by `updatedAt`) to
  see whether that turn asked something.
- `coordinator/mods/cockpit/main.js` places groups with `place` and
  adds the Dead runs column, collapsed by default (`dead-open` in local
  storage remembers a change).
- `coordinator/mods/cockpit/ui.js` gives the column its header, the ask card
  its Decisions button, and the ask decision its own overlay.

## Proof

`proof.mjs` runs the classifier over the state Shyam reported (33 failed and
21 stopped cards, nothing asking) and then loads the real board through the
real loader with a standing in for the `herdr` runtime module, so the T3 calls
are the live ones.

### Offline

`node proof.mjs --offline` runs the deterministic half only. It stops before
the runtime adapter is registered, before `hub.js` is imported or loaded,
before the temporary decisions file is written, and before any T3 call, so it
needs no live board and no credentials. The classifier it exercises is the
real `coordinator/mods/cockpit/asks.js`, so an offline run still fails when
the classifier regresses. It exits 0 when every check passes and 1 when one
does not.

### Live

```
cd evidence/board-needs-you
PROOF_DECISIONS_ITEMS='[]' node proof.mjs                                  # needs 0, dead 54
PROOF_DECISIONS_ITEMS='[{"id":"x","group":"mac-ops","title":"Approve the frame reboot window?","why":"..."}]' node proof.mjs
PROOF_DECISIONS_ITEMS='[{"id":"x",...},{"id":"y",...}]' node proof.mjs    # two decisions, no task id: two groups
```

It also checks placement, not only the classifier: a finished turn that asks
with an open PR lands in Needs you, a quiet one with an open PR stays in Ready
to merge, and no asked group on the real board sits in Ready.

The offline run covers the mixed group too: a group that is still running and
also holds a thread whose turn ended by asking is counted as an ask, in
either thread order, and it beats a mergeable PR. The same mixed group with a
quiet thread stays a run, and a quiet dead group stays dead. Reverting the
ask-before-run order in `asks.js` makes the offline run fail.

`proof.txt` is all three runs together. The live board showed `needs 1` (a
finished turn asking a real question) and `dead 3`; one decision took needs to
2, two decisions to 3, and dead stayed 3. The ask cards keep their key, their
time and their own group.
