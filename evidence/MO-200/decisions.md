# MO-200 decisions

Refs #163. Ticket: https://github.com/shyamsivakumar/mac-ops/issues/163
Run id: `ticket:shyamsivakumar/mac-ops#163:a3` (attempt 1 ran and produced no
PR; attempt 2 landed the check in PR #204; this attempt fixes two gaps the
landed check still had against the same brief).

## Revision 2: what changed

Attempt 2 landed the text blocker check (`b43b4e4`, PR #204). This attempt
keeps that behaviour and closes two gaps between the landed check and the
brief's stated behaviour change. Both gaps let a ticket whose body names an
unmet prerequisite start anyway.

- `coordinator/bin/ticket`:
  - **The `Blocked by` section is read in both forms the body uses.** The
    landed check read only a `## Blocked by` heading. The coordinator also
    writes the section as a `Blocked by:` line, and its own template check
    accepts both forms, so a body written as a line was read as having no
    section at all: no blocker was ever named. `blocked_by_section` now reads
    the heading form first and the labelled line second.
  - **A `<details>` block is not the ticket's own section.** Several repos
    keep a preserved original contract inside `<details>`, and that contract
    carries the old `Blocked by:` line. The section reader skips `<details>`
    blocks and fenced code, so a preserved contract cannot refuse a ticket
    the coordinator has since approved.
  - **A key resolves by the title prefix `<KEY>-<n>`, whatever separator
    follows.** The landed check matched the exact prefix `<KEY>-<n> ·`. The
    newest SRW tickets are titled `SRW-1119: Hash-route tabs`, so their keys
    resolved to nothing and the refusal read `SRW-1119 has no issue ... whose
    title starts with 'SRW-1119 ·'`. The prefix now matches `<KEY>-<n>`
    followed by any character that is not a digit, which keeps `SRW-789` from
    matching `SRW-7890`.
- `tests/test_ticket_text_blockers.py`: 12 new unit tests (32 in the file) and
  a test isolation fix so the section tests restore the functions they patch.

Not touched: the native blocker refusal, labels, intent comments, receipt
comments, the queue, the launch path, every other subcommand and every other
existing behaviour. No existing test or check was weakened.

## Revision 1 (attempt 2): what landed

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

## Decisions (revision 2)

### 9. The `Blocked by` section is read as a heading or as a labelled line

- **When**: revision 2.
- **The decision**: `blocked_by_section` reads the `## Blocked by` section
  first and the `Blocked by:` line second, exactly the two forms the
  template check (`template_status`) accepts.
- **The gap**: The brief says the check reads the `## Blocked by` section.
  The landed code read only that. The coordinator's bodies carry both forms:
  SRW #1015 to #1019 write `Blocked by: SRW-1119, SRW-1120.`, and the
  template check calls that section `ok`. A section written as a line was
  read as no section at all, so its blockers were never named.
- **The reach**: Every body written as a labelled line now has its blockers
  read. The heading form is unchanged, and a body that has both takes the
  heading.
- **Verdict**: sound.
- **Confidence**: high. The proof shows the same real body reading `None`
  before the change and `SRW-1119, SRW-1120.` after it.

### 10. A preserved contract is not the ticket's own section

- **When**: revision 2.
- **The decision**: The section reader strips `<details>` blocks and fenced
  code before it looks for the section.
- **The gap**: `shyamsivakumar/catalouge#53` keeps its original contract in a
  `<details>` block, and that contract carries `Blocked by: #49, #51, #52`.
  The coordinator's decision in the same body approves the build and names
  the native blocked-by relationships as authoritative.
- **The reach**: A preserved contract cannot refuse a ticket. The ticket's
  own `## Blocked by` section still decides, and its refs are still read.
- **Verdict**: sound.
- **Confidence**: medium. A reviewer may prefer preserved contracts to be
  read as well; the coordinator decision that overrides them is prose the
  check does not parse.

### 11. A key resolves by prefix `<KEY>-<n>`, not by the ` ·` separator

- **When**: revision 2.
- **The decision**: A title matches the key when it starts with `<KEY>-<n>`
  and the next character is not a digit.
- **The gap**: The brief says the key is resolved by the exact title prefix
  `<KEY>-<n> ·`. The newest SRW tickets are titled `SRW-1119: ...`, so that
  prefix matched nothing and the key was refused as unresolvable, even when
  the blocker it names was closed.
- **The reach**: `SRW-789` still cannot match `SRW-7890`. Every title that
  matched before still matches. The refusal now names the key and the issue
  number instead of claiming the key has no issue.
- **Verdict**: sound.
- **Confidence**: high.

## Decisions (revision 1)

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

### Revision 2

1. **SRW #1018 (the compact `Blocked by` line).** The same real body read as
   no section before this change and reads `SRW-1119, SRW-1120.` after it,
   so the check now refuses with `SRW-1119 (#1016) is still open` and
   `SRW-1120 (#1017) is still open`. The CLI itself stops earlier on that
   ticket (`missing type label`), because the label check runs before the
   text check, so the probe calls the same function the CLI calls.
2. **SRW #1015 (`Blocked by: none.`).** The section reads `none.` and the
   reasons are empty.
3. **catalouge #53 (a preserved contract inside `<details>`).** The section
   read is the ticket's own `## Blocked by` section, the preserved
   `Blocked by: #49, #51, #52` line is not read, and the reasons are empty.
4. **SRW #890, SRW #899, SRW #490 and `--force-text-blockers`** behave exactly
   as in revision 1; the outputs are in `evidence/MO-200/proof.txt`.
5. **Checks.** `python3 scripts/mac_ops_fast_check.py` passed (it ran the 32
   tests in the file). The full suite through heavy,
   `~/.local/bin/heavy python3 -m unittest discover -s tests -t .`, ran 148
   tests, OK.

### Revision 1

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
