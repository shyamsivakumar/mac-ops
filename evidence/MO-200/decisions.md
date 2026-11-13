# MO-200 decisions

Refs #163. Ticket: https://github.com/shyamsivakumar/mac-ops/issues/163
Run id: `ticket:shyamsivakumar/mac-ops#163:a2` (attempt 1 of this ticket ran
earlier and produced no PR; the coordinator's brief names attempt 2).

## What landed

- `coordinator/bin/ticket`: two text blocker checks in the `ticket start` path,
  next to the existing native blocker check, both raising the same `Refuse`.
  - The `## Blocked by` section is read up to the next `## ` heading. Every
    `#<n>` (the ticket's own repo), every `owner/repo#<n>` and every `<KEY>-<n>`
    of the repo's own key must be a closed issue or a merged pull request.
    `<KEY>-<n>` is resolved by the exact title prefix `<KEY>-<n> ·` in the same
    repo, because a key number is not an issue number (SRW-789 is issue #490).
  - Any sentence in the body that pairs `only after` / `build only after` /
    `before building` with `review` / `approval` / `verdict` refuses unless a
    verdict is recorded. The refusal names the sentence.
  - `--force-text-blockers` skips both checks and says so. Native blockers
    still apply.
- `tests/test_ticket_text_blockers.py`: 20 unit tests over the section
  reader, the sentence reader, the reference checks and the refusal seam.

Not touched: the native blocker refusal, labels, intent comments, receipt
comments, the queue, the launch path, every other subcommand and every other
existing behaviour. No existing test or check was weakened.

## Decisions

### 1. The text check sits after the native blocker check and its reasons join the native refusal

- **When**: revision 1.
- **The decision**: `validate_start` keeps its order. The native blockers are
  read first and the text reasons are appended to that refusal as
  `; text blockers: ...`. A ticket with only native blockers keeps the exact
  refusal line it had before.
- **The gap**: The brief asks for "the same `Refuse` error" and for the check
  to live next to the native one, but says nothing about which refusal wins
  when a ticket has both.
- **The reach**: A future blocker kind can be added the same way: compute the
  reasons, append them to the native refusal, keep the native line intact.
- **Verdict**: sound.
- **Confidence**: high.

### 2. A closed ticket also carries the text reasons

- **When**: revision 1.
- **The decision**: The `issue is closed` refusal gains the text reasons as a
  suffix when the body names unmet prerequisites.
- **The gap**: The brief proves the new check on SRW #890, and #890 was closed
  by the time this ran. Without the suffix, `ticket start` on #890 would say
  only "issue is closed" and the missing design review would never be named.
- **The reach**: The ticket cannot start either way, so the extra text changes
  no outcome. It only tells the reader why the ticket would have stopped at
  once.
- **Verdict**: sound.
- **Confidence**: medium. A reviewer may prefer the closed refusal to stay
  short.

### 3. Only the repo's own key counts as a key reference

- **When**: revision 1.
- **The decision**: `SRW-1018` is read as a blocker in the SRW repo and `MO-9`
  in the mac-ops repo. `PR-905` or `JIRA-12` are left alone.
- **The gap**: The brief says "every `<KEY>-<n>`", and a body can mention a
  foreign key for a ticket in another tracker.
- **The reach**: A foreign key cannot be resolved in the same repo, so reading
  it as a blocker would refuse every ticket that mentions one.
- **Verdict**: sound.
- **Confidence**: high.

### 4. A verdict is a comment, never the body

- **When**: revision 1.
- **The decision**: The verdict clears the approval refusal when a comment URL
  in the body or in a comment on the ticket points at a comment whose text
  contains `VERDICT: PASS`, or when a comment on the ticket itself carries
  `VERDICT: PASS`. The body alone is not evidence.
- **The gap**: The brief says "the body or an issue comment links a comment URL
  whose text contains `VERDICT: PASS`". Read literally the body can only
  carry the link.
- **The reach**: Every ticket body ends with the gate line `Final line exactly
  VERDICT: PASS or VERDICT: FAIL`. If the body counted, the approval check
  would never refuse anything.
- **Verdict**: sound.
- **Confidence**: high.

### 5. A key that cannot be resolved is refused by name

- **When**: revision 1.
- **The decision**: `SRW-4242` with no issue titled `SRW-4242 ·` in the repo is
  refused as `SRW-4242 has no issue in <repo> whose title starts with
  'SRW-4242 ·'`.
- **The gap**: The brief says a key must "be a closed issue or a merged PR".
  An unresolved key is neither, but it may also be a renamed or deleted issue.
- **The reach**: The refusal names the key, so the reader can fix the body.
  A ticket that mentions a key only in passing can be forced through with
  `--force-text-blockers`.
- **Verdict**: sound.
- **Confidence**: medium.

### 6. A closed pull request that never merged does not clear a blocker

- **When**: revision 1.
- **The decision**: Only a merged pull request clears a blocker. A pull request
  that was closed without merging is refused as `is not merged`.
- **The gap**: The brief says "a closed issue or a merged PR", so the two are
  different states and need different checks.
- **The reach**: The check reads `merged` from the pull request API, so a
  closed PR is never mistaken for a closed issue.
- **Verdict**: sound.
- **Confidence**: high.

### 7. "None" as the first line of the section means no blockers

- **When**: revision 1.
- **The decision**: A `Blocked by` section whose first line is `None` passes,
  even when the section continues with prose such as "None. This is the
  frontier ticket and can start immediately."
- **The gap**: The brief says "None or an empty section passes". It does not
  say whether prose after "None" is still a blocker list.
- **The reach**: A section that starts with "None" and then names a key is
  read as no blockers, which matches how the section is written in the board.
- **Verdict**: sound.
- **Confidence**: medium.

### 8. The CLI script is importable so the new checks have unit tests

- **When**: revision 1.
- **The decision**: The last line of `coordinator/bin/ticket` is now
  `if __name__ == "__main__": main()` instead of a bare `main()`.
- **The gap**: The CLI is a script without a `.py` suffix, so a test could not
  import it without executing the whole program.
- **The reach**: The installed CLI behaves the same: it is run as a script, so
  `__name__` is `__main__` and `main()` runs exactly as before.
- **Verdict**: sound.
- **Confidence**: high.

## Proof

The proof outputs are in `evidence/MO-200/proof.txt` and in the pull request
body.

1. **SRW #890 (the ticket from the brief).**
   `python3 coordinator/bin/ticket start shyamsivakumar/strategy-replay-workbench#890 --dry-run`
   refuses and names the missing design review:
   `refused: issue is closed; text blockers: SRW-789 (#490) is still open; the
   body requires an approval before building: "Build only after the separate
   Opus design review the design document requires; ..."`.
   The brief allowed this refusal to disappear if a PASS verdict exists. One
   does exist, as a comment on #490 (`issuecomment-6845589631`, "passed its
   separate Claude Opus 5.5 gate (VERDICT: PASS)"), but the ticket body links
   no comment URL and SRW-789 (#490) is still open, so both rules refuse.
   That comment is on another issue, and the section rule names SRW-789 (#490)
   itself, so the ticket stays refused.
2. **SRW #899.** Refused, naming SRW-1018 and its open issue, with the native
   refusal kept in front: `refused: blocked by open
   shyamsivakumar/strategy-replay-workbench#806; text blockers: SRW-1018 (#806)
   is still open`.
3. **A ticket with `Blocked by: None` passes.** SRW #1002 (`## Blocked by`
   `None.`) printed `checks passed` on a dry run at 08:51 while it still
   carried `stage:todo`; the coordinator started it a minute later and the
   label is now gone, so the same command now stops at the label check. The
   unit tests keep this case: `test_none_section_passes` and
   `test_none_with_prose_passes`.
4. **`--force-text-blockers`.** On #890 the text check no longer refuses
   (`refused: issue is closed`); on #899 the native blocker still refuses
   (`refused: blocked by open ...#806`). The skip is printed on both.
   `test_force_skips_the_text_blockers` shows a ticket whose only problem is
   a text blocker starting when the check is off.
5. **Checks.** `python3 scripts/mac_ops_fast_check.py` passed (it ran the 20
   new tests). The full suite through heavy,
   `~/.local/bin/heavy python3 -m unittest discover -s tests -t .`, ran 134
   tests, OK.

## After the merge

```sh
cd <mac-ops checkout on merged main> && python3 install_coordinator.py
```

The installer writes `coordinator/bin/ticket` to `~/.local/bin/ticket`.

## Rollback

Revert the squash commit and run the installer again.

## Known gap, out of scope here

A verdict recorded only on the blocking issue (SRW #490) does not clear the
approval rule for a ticket that does not link it. The brief's wording puts the
verdict in the ticket body or in a comment on the ticket, so this stays as it
is until the brief says otherwise.
