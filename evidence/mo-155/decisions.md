# Decisions ledger — MO-155

Decisions this ticket did not cover, in the dzhng audit-decisions format:
every entry carries when it landed, the decision in plain words, the gap it
closes, its reach, a verdict and a confidence. Groups run needs-user, unsound,
sound; within a group, least confident first. `evidence/mo-155/decisions.md`.

## Sound

### The ledger format follows dzhng's audit-decisions, not only the ticket's field list

**When:** MO-155 closeout, 2026-11-10 PT.

*The ticket names six fields (when, the decision, the gap, the reach, a verdict,
a confidence) but not how an entry reads. dzhng's audit-decisions, vendored by
LMW-58 at 873aba8d, gives each entry a one-line headline plus a walked
scenario — the triggering event, what the work does today, what the unbuilt
alternative would have done — and groups entries by verdict so the reader sees
needs-user first. This rule writes the six fields with that shape: groups
needs-user, then unsound, then sound, and each group ranked least confident
first, so the reader opens with the calls they are least sure of.*

**Gap:** the ticket said "rank least confident first" as one flat rule; that
silently conflicts with dzhng's verdict grouping, and nothing said which of the
two wins.

**Reach:** every ledger written from here on carries the shape, and LMW-58's
vendored skill text has to agree with it or the two will drift.

**Verdict:** sound — the ticket pointed at dzhng's format as the reference and
only summarised its fields, so the summary was read as a compression, not a
different format.

**Confidence:** medium — LMW-58 has not landed, so the vendored wording could
still differ in detail; reconcile the two when it lands.

**Owner:** `empryo/config/EMPRYO.md:44`

### `<KEY>` is the repo key lowercased plus the issue number

**When:** MO-155 closeout, 2026-11-10 PT.

*The ticket asks for `evidence/<KEY>/decisions.md` without saying what `<KEY>`
is. This rule defines it as the ticket key: the repo key lowercased plus the
issue number, `mo-155` for shyamsivakumar/mac-ops#155, which is the shape
the evidence files in this repo already use (`evidence/mo-154-hub-proof.md`).
The alternative — the raw issue number, the branch name, or the run id
`ticket:<repo>#<n>:a<attempt>` — puts a slash or a colon inside a directory
name, or scatters the same ticket's evidence under two names.*

**Gap:** the ticket left the directory name undefined, so two agents working
the same ticket could write two ledgers in two places.

**Reach:** the path in the closeout rule and the reviewer's check; a repo with
no key in `empryo/config/tickets.json` has no obvious form for it.

**Verdict:** sound — the repo already names evidence this way.

**Confidence:** medium — the key-to-repo mapping lives in a config file that
grows, and a repo without a key needs a fallback.

**Owner:** `empryo/config/EMPRYO.md:44`

### Docs-only and config-only tasks may write a one-line "No undecided choices"

**When:** MO-155 closeout, 2026-11-10 PT.

*The ticket's "Must not cause" exempts docs-only and config-only tasks from
the rule and says such a task may write "No undecided choices" with a one-line
reason. This rule keeps that exemption optional rather than mandatory: the
file may hold that single line, and the reviewer does not ask for more. A
docs-only change still can hide a real choice — a renamed config key, a
dropped flag — so the one-liner asks the task to say it considered them.*

**Gap:** the ticket said what such a task may write but not whether it must
write anything at all.

**Reach:** every docs-only or config-only task, and the reviewer's severity
call on them.

**Verdict:** sound — matches the ticket's wording, and "may" is the weaker
claim the ticket used.

**Confidence:** medium — Shyam may want the one-liner mandatory so a decision
never goes unrecorded, even on small changes.

**Owner:** `empryo/config/EMPRYO.md:44`

### The reviewer's ledger check applies to every repo except the five Ascend ones

**When:** MO-155 closeout, 2026-11-10 PT.

*Ascend repos keep their tickets in Linear, so they never close with an
Empryo task and never need a ledger. The reviewer prompt therefore excludes
them by name and treats everything else as a personal repo, including a repo
whose task carries no GitHub ticket. The alternative — ask the reviewer to
judge "personal" from the ticket or the repo owner — makes the check depend on
the reviewer's guess; the ticket's own wording is "excluded by repo name".*

**Gap:** the ticket says "personal-repo" without a test that a reviewer can
apply, and the reviewer's prompt is the only place the test could live.

**Reach:** the reviewer's severity call on tasks in repos with no ticket, and
on any future Ascend repo that is not one of the five named.

**Verdict:** sound — fails toward asking for the ledger, which is the
direction the ticket's "empty ledger on non-trivial work is a red flag" points.

**Confidence:** medium — a task in a repo that is not on either list may get a
ledger it does not need.

**Owner:** `empryo/config/agents/code-reviewer.md:26`

### No unit test asserts the wording of the two prompt files

**When:** MO-155 closeout, 2026-11-10 PT.

*The change edits two markdown prompt files. A test could assert that the
closeout rule and the reviewer check are present, but the ticket asks for the
diff and the existing suite, and the repo's own rule says new checks go in new
files only when the task asks for them. A test that greps prose for a phrase
would break on every rewording of the rule and would prove nothing about
whether an agent follows it.*

**Gap:** the ticket did not say whether the rule needs a check of its own.

**Reach:** future edits to these files; the suite stays green because it does
not read them.

**Verdict:** sound — the proof asked for is the diff plus the existing tests.

**Confidence:** medium — a smoke check on the installed prompts could catch a
rule that never reaches `~/.empryo`, which this repo cannot see.

**Owner:** `empryo/config/EMPRYO.md:44`

### The ledger is committed with the change, not merely written

**When:** MO-155 closeout, 2026-11-10 PT.

*The ticket says the task writes `evidence/<KEY>/decisions.md` and links it
from its done report. An untracked file satisfies that sentence literally and
still fails at the point of the rule: the reviewer reads the diff, and Shyam
reads the PR. This rule therefore says to commit the ledger with the change,
so it ships inside the PR the reviewer and Shyam open.*

**Gap:** the ticket did not say whether the ledger is committed, and "writes"
reads both ways.

**Reach:** every ledger; an untracked one leaves the rule satisfied on paper
and empty in practice.

**Verdict:** sound — the rule's whole purpose is that the decisions reach the
reader.

**Confidence:** high.

**Owner:** `empryo/config/EMPRYO.md:44`

### The Ascend repos are named in full, not as the ticket's abbreviations

**When:** MO-155 closeout, 2026-11-10 PT.

*The ticket lists the Ascend repos as AUH, MCP, OPS, DBT and OMN. Read
literally, "OPS" is mac-ops, which is a personal repo, and "MCP" is not a
repository name on its own. The rule names the five repos this repo's own
design doc names: AUH, ascend-mcp, data-ops, dbt and omni, the slash-eureka
repos whose tickets live in Linear.*

**Gap:** the ticket's abbreviations do not match repository names, so an
agent checking "is this repo excluded?" by name would misread two of the five.

**Reach:** both the closeout rule and the reviewer's exclusion list; a repo
named wrongly is excluded wrongly, in either direction.

**Verdict:** sound — the full names come from `docs/local-tickets-design.md`
in this repo.

**Confidence:** high.

**Owner:** `empryo/config/EMPRYO.md:44`

### One in-session review round ran even though this change is config-only

**When:** MO-155 closeout, 2026-11-10 PT.

*The global rules tell an agent to skip the code-reviewer dispatch for
docs-only and config-only changes. This ticket's Finish section says to run
one in-session review round. The task-specific instruction wins, and the
reviewer also gets to see the new check in the file it governs.*

**Gap:** the two instructions point in opposite directions for this change
alone.

**Reach:** this task only; the general skip rule for docs-only and config-only
changes is untouched.

**Verdict:** sound — the ticket's own Finish section asks for the round.

**Confidence:** high.

**Owner:** `empryo/config/agents/code-reviewer.md:26`
