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
  turn's last line, and `columnOf` decides the column for a group of threads.
- `coordinator/mods/cockpit/hub.js` reads `decisions.json` as cards, and reads
  the tail of each finished thread once per change (cached by `updatedAt`) to
  see whether that turn asked something.
- `coordinator/mods/cockpit/main.js` places groups with the classifier and
  adds the Dead runs column, collapsed by default (`dead-open` in local
  storage remembers a change).
- `coordinator/mods/cockpit/ui.js` gives the column its header, the ask card
  its Decisions button, and the ask decision its own overlay.

## Proof

`proof.mjs` runs the classifier over the state Shyam reported (33 failed and
21 stopped cards, nothing asking) and then loads the real board through the
real loader with a standing in for the `herdr` runtime module, so the T3 calls
are the live ones.

```
cd evidence/board-needs-you
PROOF_DECISIONS_ITEMS='[]' node proof.mjs                                  # needs 0, dead 54
PROOF_DECISIONS_ITEMS='[{"id":"x","group":"mac-ops","title":"Approve the frame reboot window?","why":"..."}]' node proof.mjs
PROOF_DECISIONS_ITEMS='[{"id":"x",...},{"id":"y",...}]' node proof.mjs    # two decisions, no task id: two groups
```

`proof.txt` is all three runs together. The live board showed `needs 1` (a
finished turn asking a real question) and `dead 3`; one decision took needs to
2, two decisions to 3, and dead stayed 3. The ask cards keep their key, their
time and their own group.
