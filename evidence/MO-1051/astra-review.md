# MO-1051 review round

One in-session Astra Medium review ran on the pushed diff of the first turn
(`7b9fb0d`, branch `t3/normalize-ticket-section-headings`). It returned FAIL
with three blocking findings and one worth fixing. No second reviewer round
was requested; the builder fixed the findings and re-verified.

Findings and what the builder did:

- Blocking, `coordinator/bin/ticket`: normalization turned list content into
  a section marker, so a body with `Context:` and then `- Context: ...` lost
  the text of the `Context` section and was refused as empty. The label line
  now has to start at the start of the line, the way the old exact match read
  it. Covered by `test_a_list_item_is_not_a_section_label`.
- Blocking, `coordinator/bin/ticket`: `[^a-z0-9]+` stripped more than the
  separators the ticket names, so `Contexté` read as `Context` and `CI++` read
  as `CI`. The canonical form now splits on whitespace, `/` and `,` only.
  Covered by `test_a_non_ascii_letter_is_not_a_separator` and
  `test_a_letter_is_not_a_separator`.
- Blocking, `coordinator/bin/ticket`: the canonical helper and the label
  pattern sat at module level, outside the function the ticket names. Both
  now live inside `template_markers`.
- Worth fixing, `tests/test_ticket_section_headings.py`: the configuration
  assertion compared the configured list with itself and could not fail, and
  the fixtures exercised only the label form, so the Markdown heading branch
  was untested. The test now compares the configured list with the twelve
  names written out in order, and a new fixture
  `tests/fixtures/ticket_start/heading/body.md` writes every section as a
  Markdown heading, including `## Data, secrets and stop conditions`.

Verification after the fixes:

- `python3 -m unittest tests.test_ticket_section_headings`: 16 tests, all
  pass.
- The same test file against `origin/main` fails 8 of its 16 tests, so the
  tests fail when the fix is reverted.
- `python3 tests/ticket_start_proof.py`: four `ticket start --dry-run` runs
  on the real CLI, the comma label passes, the comma heading passes, the
  deleted section still reports
  `Data/secrets and stop conditions (missing)`, and the configured name still
  passes.
- `heavy python3 scripts/mac_ops_fast_check.py`: `fast-check: passed`.
