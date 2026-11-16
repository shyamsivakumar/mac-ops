# #277 delivery plan

Refs #277. Resume approval: 2026-11-16. Twenty-minute turn, commands under timeout
300, no live sends or tests beyond the required repo check. Start from fresh main.

Adapt the PR actions to the current lane driver, share the classifier with board,
and dedupe queue insertion under its existing lock. Preserve reviewer and cap
rules. Inspect the diff in one in-session reviewer round. Run the repo check,
record its actual result, commit, push and open a ready PR. No merge by this task.
Pass criterion: each eligible stalled PR has an action; no duplicate queued action
for a head; failed checks cannot gate; shift PR handler does not merge/close.
Missing proof goes in Left for later without editing an existing test/check.
