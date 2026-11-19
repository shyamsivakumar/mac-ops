# Resolve a key to an issue only, and read the section the template check read (Refs #163)

Refs #163

Run id: `ticket:shyamsivakumar/mac-ops#163:a3`
Head SHA: `869fecbad9898158b1a587482d3392fede5cc020`

Follow-up to #206, which merged with the first commit of this branch. These
are the fixes the in-session review round (Opus, Claude Opus 5.5) asked for
on that commit.

## What changed

- `coordinator/bin/ticket`:
  - **A key resolves to an issue, never to a pull request.** The key search
    has no `is:issue` filter and GitHub sorts results by best match. With
    the looser title prefix from #206, a merged pull request titled
    `SRW-1018 part 1: ...` could answer for the key `SRW-1018` while the
    issue it names was still open. The query now asks for issues and every
    result with a `pull_request` field is skipped. This was the reviewer's
    major finding.
  - **The section read is the one the template check read.** The section
    reader now uses the same markers as `template_status`, so the blocker
    check looks at exactly the section the template check accepted. A
    `Blocked by:` line is read as its own value plus any list under it. The
    first version read only the rest of that line, so a list under the label
    read as empty, a false pass. This was the reviewer's second minor
    finding.
  - A bold `**Blocked by:**` value no longer keeps its leading `**`, and a
    list-item label is read the same way the template check reads it, so the
    two checks agree. These were the reviewer's remaining minor findings.
- `tests/test_ticket_text_blockers.py`: 4 new tests for the pull request
  filter, the `is:issue` query, the list under a labelled section, and the
  section matching the template check (36 in the file).

Not touched: the native blocker refusal, labels, intent comments, receipt
comments, the queue, the launch path, every other subcommand. No existing
test or check was weakened.

## Proof

```
Revision 2 (run ticket:shyamsivakumar/mac-ops#163:a3). The text blocker check
itself landed in attempt 2 (b43b4e4, PR #204). This attempt closes three
gaps between the landed check and the brief: the `Blocked by` section was read
only as a `## Blocked by` heading, a key resolved only by the `<KEY>-<n> ·`
title prefix, and a key could resolve to a pull request.

$ python3 coordinator/bin/ticket start shyamsivakumar/strategy-replay-workbench#890 --dry-run
refused: issue is closed; text blockers: SRW-789 (#490) is still open; the body requires an approval before building: "Build only after the separate Opus design review the design document requires; if no such verdict is recorded, stop with `WAITING:` and name the missing approval."

$ python3 coordinator/bin/ticket start shyamsivakumar/strategy-replay-workbench#899 --dry-run
refused: blocked by open shyamsivakumar/strategy-replay-workbench#806; text blockers: SRW-1018 (#806) is still open

$ python3 coordinator/bin/ticket start shyamsivakumar/strategy-replay-workbench#490 --dry-run
checks passed

$ python3 coordinator/bin/ticket start shyamsivakumar/strategy-replay-workbench#1018 --dry-run
refused: missing type label

$ python3 coordinator/bin/ticket start shyamsivakumar/strategy-replay-workbench#1018 --dry-run --force-text-blockers
text blocker checks skipped (--force-text-blockers)
refused: missing type label

$ python3 coordinator/bin/ticket start shyamsivakumar/strategy-replay-workbench#890 --dry-run --force-text-blockers
text blocker checks skipped (--force-text-blockers)
refused: issue is closed

The `Blocked by` section of the same real bodies, read with the landed check
and with this change. The probe calls the function the CLI calls, because the
CLI stops on SRW #1018 earlier, at the label check ("missing type label"), and
the label check runs before the text check.

$ git show origin/main:coordinator/bin/ticket > /tmp/old_ticket.py   # the landed check
$ python3 evidence/MO-200/section_probe.py /tmp/old_ticket.py 1018 shyamsivakumar/strategy-replay-workbench
body section: None
reasons: []

$ python3 evidence/MO-200/section_probe.py coordinator/bin/ticket 1018 shyamsivakumar/strategy-replay-workbench
body section: 'SRW-1119, SRW-1120.'
reasons: ['SRW-1119 (#1016) is still open', 'SRW-1120 (#1017) is still open']

$ python3 evidence/MO-200/section_probe.py coordinator/bin/ticket 1015 shyamsivakumar/strategy-replay-workbench
body section: 'none.'
reasons: []

$ python3 evidence/MO-200/section_probe.py coordinator/bin/ticket 53 shyamsivakumar/catalouge
body section: 'Use existing native GitHub blocked-by relationships as authoritative; preserve them. Parent/spec links are context, not additional blocking edges. stage:todo is queued, not permission to bypass prerequisites.'
reasons: []

$ python3 evidence/MO-200/section_probe.py coordinator/bin/ticket 490 shyamsivakumar/strategy-replay-workbench
body section: 'None.'
reasons: []

$ python3 -m unittest tests.test_ticket_text_blockers
....................................
----------------------------------------------------------------------
Ran 36 tests in 0.003s

OK

$ python3 scripts/mac_ops_fast_check.py
fast-check: passed; selected checks are not the full suite

$ ~/.local/bin/heavy python3 -m unittest discover -s tests -t .
Ran 152 tests in 3.022s

OK
```

## Checks

```
$ python3 scripts/mac_ops_fast_check.py
fast-check: passed; selected checks are not the full suite

$ ~/.local/bin/heavy python3 -m unittest discover -s tests -t .
Ran 152 tests in 3.022s

OK
```

Builder check: PASS 869fecbad9898158b1a587482d3392fede5cc020

## After the merge

```sh
cd <mac-ops checkout on merged main> && python3 install_coordinator.py
```

The installer writes `coordinator/bin/ticket` to `~/.local/bin/ticket`.

The repository is at `/app`. Make the change there. Do not edit test files.
