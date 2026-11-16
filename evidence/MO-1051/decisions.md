# MO-1051 decisions

The ticket asked for one change in `coordinator/bin/ticket`: compare a
heading's words after normalizing case, spacing and separator punctuation, so
`/`, `,` and ` and ` between the same words name one section. These are the
decisions the ticket did not cover.

## The word "and" is a separator, not part of the name

When: 2026-11-16, in the builder turn for `ticket:shyamsivakumar/mac-ops#469:a1`.

Decision: the canonical form of a section name is its lower-case words with
`/`, `,` and the word `and` dropped between them, so the configured
"Data/secrets and stop conditions" and the written "Data, secrets and stop
conditions" both canonicalize to "data secrets stop conditions".

Scenario: a ticket writes "Data and secrets and stop conditions". It matches
the configured section, because "and" only ever sits between words of a
section name.

Gap: the ticket says "and" is one of the separators that count as the same
section, but it does not say whether "and" is dropped from the name or only
treated as a separator when the same words surround it.

Reach: every configured section that contains the word "and": "Goal and why",
"Acceptance and proof", "Data/secrets and stop conditions", and any section a
future ticket adds with "and" in it.

Verdict: sound. Confidence: high. The two spellings the ticket names
canonicalize to the same form, and no configured section loses a word that
another section needs.

## Two configured names that canonicalize alike would collide

When: 2026-11-16, same turn.

Decision: when two configured section names canonicalize to the same form,
the first one in the configured order wins.

Scenario: a future configuration adds "Data/secrets and stop conditions" and
"Data secrets stop conditions" as two sections. One heading would then match
only the first, and the second would be reported missing even though the
heading names it.

Gap: the ticket does not say how to resolve a collision, and today's twelve
configured names canonicalize to twelve different forms.

Reach: only a configuration that adds such a pair. Today's configuration is
unaffected, and the configured list and its order are unchanged by this
change.

Verdict: sound. Confidence: medium. The rule is deterministic and matches the
"first marker wins" behaviour the rest of the CLI already uses, but no real
collision exists yet to prove it.

## A labelled line is matched by its label, not by a fixed name

When: 2026-11-16, same turn.

Decision: the label branch of the marker check reads the label from the line
and compares it canonically, instead of testing the configured name against
the line one name at a time.

Scenario: the body line "**Data, secrets and stop conditions**: repo files
only." is read as the configured section, with the text after the colon as
its content.

Gap: the ticket names the heading check; the same body can carry the section
as a label line, which the to-tickets skill template writes, and the old
label branch matched only the exact configured name.

Reach: every line of every ticket body that is not a heading. A line whose
text before the first colon canonicalizes to a configured name is read as that
section; every other line is left alone, as before.

Verdict: sound. Confidence: high. The behaviour on names that need no
normalization is unchanged, and the existing blocker and approval checks
still read the section the template check accepted.

## The proof uses a local fixture, not a live ticket

When: 2026-11-16, same turn.

Decision: the three proofs run the real CLI with the GitHub read answered by a
stub in `tests/fixtures/ticket_start/ghstub`, so no issue on GitHub is
created, edited or started.

Scenario: `python3 tests/ticket_start_proof.py` prints the output of three
`ticket start --dry-run` runs: the comma heading passes, the deleted heading
still reports the section missing, and the configured heading still passes. A
live ticket that passes today, `digitized/Concerning#32`, is also checked
read-only.

Gap: the ticket asks for the outputs of `ticket start <repo>#<n> --dry-run`
on a ticket body with the comma heading. No live ticket carries that heading
and passes the other checks: the two SRW tickets with it are closed or
merged, and `shyamsivakumar/mac-ops#469` and `shyamsivakumar/mac-ops#470`
are refused earlier for a missing stage label and for an open pull request.
Writing a ticket to get one was out of scope, so the fixture stands in.

Reach: the proof path only. The matcher itself is exercised by the same
fixture through the real CLI, and by the unit tests in
`tests/test_ticket_section_headings.py`.

Verdict: sound. Confidence: medium. The real command runs on the real
source; only the GitHub read is stubbed, and the live ticket shows that a
ticket which passes today still passes.

## Only the named separators are separators

When: 2026-11-16, in the fix turn after the review round.

Decision: the canonical form of a section name splits on whitespace, `/` and
`,` only, and drops the word `and`. Every other character belongs to a word.

Scenario: a ticket writes a heading `Contexte`. It is a different section
from `Context`, and it is reported missing.

Gap: the first turn split on every character that is not an ASCII letter or
digit, so `Contexte` and `CI++` read as `Context` and `CI` and were accepted.
The review round found it.

Reach: every section name and every heading. The ticket names `/`, `,` and
` and ` as the separators, and this is exactly those.

Verdict: sound. Confidence: high. The named spellings still match, and a
name that differs by a letter no longer matches.

## A label line starts at the start of the line

When: 2026-11-16, same turn.

Decision: a label line is a line that begins, after optional whitespace and
optional bold, with the section name and then a colon. A list item such as
`- Context: ...` is not a label line.

Scenario: a body writes `Context:` and then the bullet `- Context: The skill
writes ...`. The bullet is body text. The `Context` section keeps that text
and is not empty, so the ticket still starts.

Gap: the first turn read the label as everything before the first colon, so a
bullet that repeated a section name became a second marker for that section
and cut the first one short, which turned a passing section into an empty
one. The review round found it.

Reach: every line of every ticket body that is not a heading. The old exact
match read a label only at the start of the line, and this keeps that.

Verdict: sound. Confidence: high. The old rule rejected a bullet for the
same reason, and the old rule passed every body that passed today.

## The matcher stays inside `template_markers`

When: 2026-11-16, same turn.

Decision: the canonical form and the label pattern live inside
`template_markers`, and no new module-level name is added to the CLI.

Scenario: a reader of `coordinator/bin/ticket` finds the whole rule in the
one function the ticket names.

Gap: the first turn added a module-level helper and a module-level pattern.
The review round read that as wider than the ticket's scope.

Reach: the file only. Nothing else reads either name.

Verdict: sound. Confidence: medium. The behaviour is the same; the rule only
says where the code sits.
