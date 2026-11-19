# Risk tiers for the review gate

Revision 1, 2026-11-18. Design only: nothing described here is built. The
building ticket comes after Shyam reads this note.

Source: Coder's improvements list for mac-ops, item 1, approved by Shyam on
2026-11-17 (`~/Code/coordinator/inbox/2026-11-17-improvements-from-coder.md`):
"Risk tiers enforced by the gate; protected paths in config (lane/gate/
permission code, SRW order + trading paths, deploy files) need stronger checks
or Shyam." Filed as mac-ops#500.

## Goal

The gate applies one bar to every pull request. A README change and a change
to the code that decides which agent runs next, or to the code that places an
order, are reviewed the same way. This note names the tiers, the paths in
each tier, and what each tier requires, so the gate can read one config file
and apply the right bar.

Out of scope: changing any permission, guard, sandbox or access rule. This
note changes no code.

## What the gate does today

- One bar, `GATE_BAR` in `coordinator/bin/gate_bar.py`, for every pull
  request. Missing proof does not block, with one exception: a diff that
  changes stop logic, exit logic or trade execution keeps the full proof bar.
- One brief builder, `build_gate_brief` in `coordinator/bin/gate_policy.py`.
  It decides what the gate may do at the end: merge the pull request, or stop
  at the verdict. Today that choice comes from the repository settings
  (`merge: manual` in the coordinator config) and from whether the repository
  is an Ascend repository.
- The brief never sees the list of changed files. It reads the ticket, the
  diff, and the proof file, but it cannot say "this pull request changes the
  lane driver".

So the tier has to be computed from the pull request's changed files, and it
has to reach the brief as one value.

## The design in one line

One config file in the coordinator config names the protected paths; the gate
reads the pull request's changed files, computes the highest tier those paths
match, and applies that tier's requirements to the brief.

## The tiers

Three tiers. A path can sit in more than one tier, and the highest tier that
matches wins. A pull request that touches no protected path is tier 0 and
reads exactly as it reads today.

A tier can only add a restriction. It never removes one: tier 0 keeps the
repository's existing merge rule, so a repository that already stops at the
verdict (an Ascend repository) or that already merges by hand
(`merge: manual` in the coordinator config) stays that way.

| Tier | Name | What it covers | What the gate requires | Merge |
| --- | --- | --- | --- | --- |
| 0 | routine | every file not matched by a higher tier | today's gate bar; the proof file is optional; missing proof does not block | the repository's existing rule, unchanged: a personal repository merges on `VERDICT: PASS`, a repository that already stops at the verdict still stops there |
| 1 | protected | lane, gate, permission, deploy and policy code | the full local check must have run on the exact head (the proof file must exist and every row in it must be `passed`; a `not run` row is a finding, and a missing proof file is a finding); the gate states the tier and the matched paths in its one-line bar statement; the tier-1 checklist applies | no automatic merge: the brief ends with the existing manual ending, "Do not merge or close; Shyam merges passed PRs himself", so Shyam reads and merges |
| 2 | critical | SRW order and trading paths, and any future live-execution path | everything tier 1 requires, plus: the full proof bar of the gate bar's trade-execution exception applies (every proof the ticket asks for is required, and missing proof is a major finding); the gate brief names every matched order or trading path before the reviewer reads the diff; the tier-2 checklist applies | the gate stops at the verdict in every repository, including the ones that merge on a pass; Shyam reviews and merges |

Two words carry the whole design:

- **stronger checks** is tier 1: the proof must exist and every check in it
  must have run and passed, and the machine does not merge.
- **or Shyam** is tier 2: the machine never merges, and Shyam reads the diff.

### The checklists the tiers name

Tier 1 checklist (protected). The gate checks each of these and reports the
result in its one line:

- The proof file for the pull request exists, at `evidence/<KEY>-<issue>/check-proof.md`
  for a ticket, and every row in it reads `passed`.
- The proof file names the head of the pull request, or an ancestor of it
  whose only later change is the proof file itself.
- The brief names the tier and every matched path, and the gate says which
  bar it applied.

Tier 2 checklist (critical). Everything in tier 1, plus:

- Every proof the ticket asks for is present. The trade-execution exception
  of the gate bar already requires this; tier 2 makes it explicit.
- Every order or trading path the brief names is in the pull request's file
  list, and every path in the pull request's file list that tier 2 matches
  is in the brief. The two lists are the same list, so a name cannot be
  left out on one side.
- The gate stops at the verdict, in every repository.

What the tiers change about the bar: the gate bar says missing proof does
not block. Tier 1 and tier 2 override that sentence. On those tiers a
missing proof file, a `failed` row and a `not run` row are major findings,
and a major finding is a `VERDICT: FAIL`. On tier 0 the bar reads as it
reads today.

### Why the tiers stop the machine from merging

The repository settings already have this switch: `merge: manual` makes
`build_gate_brief` end the brief with `manual_gate_ending()`. Tier 1 and tier
2 reuse that exact string and that exact code path, so the design adds no new
merge behaviour to learn. The change is only that the switch is chosen per
pull request from the changed files, instead of per repository from the
settings.

## The paths

The list lives in the config file, not in this note. This note names the
paths that go in it, so the list can be reviewed as a list.

### mac-ops, tier 1 (protected)

Lane code:

- `coordinator/overnight/lane_driver.py`
- `coordinator/overnight/overnight`
- `coordinator/overnight/turn_cap.py`
- `coordinator/overnight/alarms.py`
- `coordinator/overnight/stall.py`
- `coordinator/overnight/board_integrity.py`
- `coordinator/overnight/selftest.py`
- `coordinator/overnight/live_smoke.py`

Gate code:

- `coordinator/bin/gate_policy.py`
- `coordinator/bin/gate_bar.py`
- `coordinator/bin/gate_reviewers.py`
- `coordinator/bin/proof_file.py`
- `coordinator/bin/close_check.py`
- `coordinator/bin/hourly_selftest.py`
- `coordinator/bin/coordq`
- `coordinator/bin/ticket`

Permission and guard code:

- `coordinator/pi/coordinator.sb` (the sandbox profile)
- `coordinator/pi/settings.json`
- `coordinator/config/hooks.json`
- `coordinator/config/AGENT-RULES.md`
- `coordinator/config/agents/code-reviewer.md`
- `scripts/cursor_agent_gate.py`
- `scripts/omp_agent_gate.py`
- `scripts/pi_agent_gate.py`
- `scripts/install_cursor_gate.py`
- `scripts/install_omp_gate.py`
- `scripts/install_pi_gate.py`
- `scripts/omp_cursor_retry.py`
- `board_governor.py`
- `board_governor.json`

Deploy files:

- `install.py`
- `install.sh`
- `install_coordinator.py`
- `install_agents.py`
- `coordinator/launchd/` (every plist in it)
- `scripts/worktree-cleaner/`
- `scripts/session-traces/`
- `scripts/install_if_behind.py`
- `scripts/shared_npm_install.py`
- `formal/install-if-behind/`

Policy code, the file that holds the tiers themselves:

- `coordinator/config/risk-tiers.json`

A pull request that changes the policy file is tier 1 at the lowest, and
its tier is computed from the live policy on the machine, not from the copy
the pull request carries. A pull request cannot lower its own bar.

### SRW (strategy-replay-workbench), tier 2 (critical)

Order and trading paths, checked against that repository's tracked files:

- `thala_v2_executor.js`
- `thala_order_attempt.js`
- `thala_v2_embed_orders.js`
- `alpaca_paper_execution.js`
- `core/fills/alpaca_paper.js`
- `bot1_trade_lane.cjs`
- `bot2/trade_machine.js`
- `cell_position_guards.js`
- `paper_execution_owners.js`
- `paper_external_order_ownership.js`
- `paper_people_execution.js`
- `order_time_receipt.js`
- `telegram_trade_loop_guard.js`
- `telegram_trade_update.js`
- `config/railway_trader_staging.json`

A path added to SRW later is not tier 2 until the list says so. The tier-2
list is exact file names, so a new order implementation is tier 0 (routine)
until Shyam adds it to the config. That is a real gap, and the note states
it rather than hiding it:

- The list is the authority. A new order file that nobody added is reviewed
  like any other file.
- Two things narrow the gap without closing it. The build ticket adds a
  check that every path in the config still exists, so a renamed or deleted
  order file shows up instead of quietly dropping out of the tier. And the
  tier-2 exception in the gate bar (a diff that changes trade execution
  keeps the full proof bar) already catches a new order file that changes
  execution, whatever the list says.
- Closing it properly needs a rule, not a longer list: a path pattern that
  covers the order and trading code of SRW wherever it lives. The design
  ticket for that belongs with the build ticket, because a pattern that is
  too wide would put ordinary SRW code into tier 2.

### mac-ops, tier 2

None today. mac-ops runs the coordinator, not the trading bots, and the brief
for this ticket says the ticket must not change bot order paths. If a mac-ops
file ever places an order or touches a live service, it goes in tier 2 and
the list is the place to say so.

## The config file

One file, next to the other coordinator config files:

- seed in this repository: `coordinator/config/risk-tiers.json`
- live copy: `~/.coordinator/risk-tiers.json`, on the Mac the coordinator
  runs on. The live copy is the policy the gate reads, the same arrangement
  as `tickets.json`: `install_coordinator.py` seeds the file when the
  machine has none and never writes over it afterwards, so a policy edit on
  the Mac is not install drift. This is how the installer treats
  `tickets.json` today: `LOCAL_CONFIG_FILES` names it, and `plan()` copies a
  name in that tuple only when `~/.coordinator/<name>` does not exist. The
  build ticket adds `risk-tiers.json` to `CONFIG_FILES` and to
  `LOCAL_CONFIG_FILES`.
  The repository copy is the seed for a new machine and the reviewable
  source of the list.

Shape:

```json
{
  "version": 1,
  "tiers": {
    "routine": { "merge": "repository-default" },
    "protected": { "merge": "manual", "require": ["proof-file-all-passed"] },
    "critical": { "merge": "stop", "require": ["proof-file-all-passed", "full-proof-bar"] }
  },
  "repos": {
    "shyamsivakumar/mac-ops": {
      "protected": [
        "coordinator/overnight/lane_driver.py",
        "coordinator/bin/gate_policy.py",
        "coordinator/launchd/",
        "install.py"
      ]
    },
    "shyamsivakumar/strategy-replay-workbench": {
      "critical": [
        "thala_v2_executor.js",
        "bot2/trade_machine.js"
      ]
    }
  }
}
```

The example shows the shape with a few entries; the real file carries the
full lists from the section above.

Matching rules:

- A path is repository-relative and uses forward slashes, the same shape the
  pull request's file list uses.
- An entry that ends in `/` matches every file under that directory.
- An entry that contains `*` matches with the same glob rules the check
  already uses for changed files. The build ticket picks one glob library and
  writes it down; the design only requires that the same function decides
  "changed file" and "protected file", so the two never disagree.
- The tier of a pull request is the highest tier among the entries its
  changed files match. Tier order is `routine` < `protected` < `critical`.
- A file that matches nothing is tier 0.
- A renamed file is two paths. The gate classifies the new path and the old
  path, and the file's tier is the higher of the two. Without this, renaming
  `coordinator/bin/gate_policy.py` to `coordinator/bin/review_policy.py`
  would match no entry on the new path, give tier 0 and allow a machine
  merge, when the old path is protected and the correct answer is tier 1 and
  a manual merge. A file that was moved out of a protected directory is
  covered the same way. A copy is not a rename: only the new path exists in
  the file list, and the new path is classified on its own.
- The tier is computed from the live config on the machine, so a pull
  request that edits the config cannot lower its own tier.

The `require` list is what a tier adds to the brief. It stays a list of short
names in the config so the gate can turn each name into a sentence, and so a
future tier can add a requirement without a new code path in the gate.

The `merge` value is a cap on what the gate may do, never a grant:

- `repository-default`: the gate does what it does today for that
  repository. A repository that merges manually still merges manually.
- `manual`: the gate stops at the verdict and Shyam merges.
- `stop`: the gate stops at the verdict and Shyam merges, and the gate says
  so in its one line, so the reviewer sees that this pull request was
  never going to merge itself.

A tier can only lower the cap. The effective cap is the lowest of the
repository's own rule and the tier's.

## Where it plugs in

The change is small and lands in two places.

1. `coordinator/bin/gate_policy.py`. `build_gate_brief` takes a tier and
   the list of changed paths, and writes two lines into the brief: the tier
   with its checklist, and the matched paths. The tier's `merge` cap is
   compared with the repository's own rule, and the lower one wins. The
   `manual` cap reuses the existing manual ending that is already in this
   file ("Do not merge or close; Shyam merges passed PRs himself"); the
   `stop` cap uses the ending that stops at the verdict.
2. The callers. `coordinator/bin/coordq` (the `gatekeep` path) and
   `coordinator/bin/ticket` (the manual `ticket gate` path) read the pull
   request's changed files, read the live config, compute the tier, and pass
   it in. The two callers use one shared function, so the manual path and the
   scheduled path cannot drift apart.

The changed-file list comes from the pull request itself, not from the local
checkout, because the gate may run on a machine that never cloned the pull
request. `gh pr view <pr> --json files` returns only the new path of a
renamed file, so the list is read with `gh api
repos/<owner>/<repo>/pulls/<n>/files --paginate`, which also returns
`previous_filename` for every rename. The shared function classifies both the
`filename` and the `previous_filename` of each entry, and the pull request's
tier is the highest tier over all of them. A list that has no
`previous_filename` field on a file whose status is `renamed` is an unreadable
list, and tier 1 is a floor for it, not a replacement: the tier is the higher
of tier 1 and the highest tier found in the paths that could be read, so a
pull request that also changes a tier-2 path stays tier 2.

That endpoint returns at most 3,000 files even with `--paginate`. The shared
function therefore also reads the pull request's own `changed_files` count
(from `gh api repos/<owner>/<repo>/pulls/<n>`, on the same head) and compares
it with the number of entries it received. If the two counts differ, or the
received count reaches 3,000, the list is incomplete. The tier is then the
higher of tier 1 and the highest tier found in the entries received, and the
brief says the list was incomplete.

## When the tier cannot be computed, it fails closed

The gate never treats an unknown situation as tier 0. Tier 0 is the only tier
that merges by machine, so every unknown becomes at least tier 1. Tier 1 is
always a floor for an unknown, never a replacement: when part of the answer is
known and higher, the higher tier wins. The one exception is a file that the
config matches nothing in: an unmatched file is tier 0 by definition, and that
is a known answer, not an unknown one.

| Situation | Tier | What the brief says |
| --- | --- | --- |
| The config file is missing | 1 | "the risk-tier config is missing, so this pull request is reviewed as protected" |
| The config file does not parse | 1 | the same, with the parse error named |
| The pull request's file list cannot be read, a renamed file carries no old path, or the list is incomplete (its entry count differs from `changed_files`, or reaches 3,000) | 1, or the highest tier found in the readable paths if that is higher | the read error or "file list incomplete" named; the gate never merges on a pull request whose files it could not fully read |
| The repository is not in the config | 1 | "this repository is not in the risk-tier config, so this pull request is reviewed as protected"; the config must list every repository the gate runs on |
| A path is listed in two tiers | the higher one | the tier named with both tiers' paths |

## What this does not change

- No permission, guard, sandbox or access rule changes. The config names
  files; it grants nothing.
- No change to the bot order paths or to any live service. The SRW paths in
  tier 2 are named so a change to them is reviewed harder, not so a change
  to them is made.
- No change to a tier-0 pull request. The same bar, the same proof rule, the
  same merge behaviour.
- No new file in the gate's read path other than the one config file, and no
  second config to keep in step with the first.

## Worked examples

**A pull request that changes `coordinator/overnight/lane_driver.py`** in
mac-ops. The lane driver is a tier-1 path. The brief carries the tier, the
matched path, the tier-1 checklist, and the manual ending. The gate reads
the diff, gives a verdict, and stops. Shyam merges.

**A pull request that changes `docs/risk-tiers-design.md`.** No tier-1 path
matches, so the tier is routine. The brief is today's brief. The gate merges
it on a pass, as it would have today.

**A pull request in strategy-replay-workbench that changes
`bot2/trade_machine.js`.** That path is tier 2. The brief names the path,
requires the full proof bar, and stops at the verdict in a repository that
would otherwise merge on a pass. Shyam reads the diff before it lands.

**A pull request that changes `coordinator/config/risk-tiers.json`** in
mac-ops. The policy file is a tier-1 path, and the tier of that pull request
is computed from the live policy on the machine, so removing a path from a
tier does not remove it from the tier the pull request is reviewed under.

## Open points for the build ticket

- The glob library, and one shared function for "changed file" and
  "protected file".
- Whether the tier shows on the board, or only in the gate brief. The brief
  alone is enough to start.
- Who may edit `risk-tiers.json`. The safest answer is Shyam only, since
  editing it can move a path out of a tier. That is a permissions question
  and this ticket does not answer it.
- Whether tier 2 should also ask for a second reviewer. The design keeps it
  to Shyam, because a second model is not a stronger authority over an order
  path.

## Left for later

- The build ticket: the config file, the tier computation, the two callers,
  and the tests.
- A check that the config's paths still exist, so a renamed file does not
  silently drop out of a tier.
- A rule that puts a new SRW order file into tier 2 without a list edit, and
  a way to keep that rule from swallowing ordinary SRW code.
- Tier 2 for mac-ops, if a mac-ops file ever places an order.
