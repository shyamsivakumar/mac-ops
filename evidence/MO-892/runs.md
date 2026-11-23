# MO-1230 runs

## On origin/main (red)
```text
AssertionError: (RECUT_BRIEF text, contains 'as many tickets as the work needs')
exit 1
```

## On the head (green)
```text
exit 0
```

## Rendered brief for a 1647-line PR
```text
Type: design · m (re-cut an oversized pull request)

Pull request shyamsivakumar/strategy-replay-workbench#868 head abc1234 counts 1647 code lines in 9 code files. One ticket may hold at most 150 code lines in 3 code files, counted the way the gate counts them.
Read the pull request with `gh pr diff 868 -R shyamsivakumar/strategy-replay-workbench`. Cut the work into at most two ordered tickets, chained with Blocked by, and never create a third ticket. Each ticket should fit that cap; when a piece cannot fit, name the work to leave for `Left for later` in the pull request or the second ticket. Each new ticket's Context names the original pull request shyamsivakumar/strategy-replay-workbench#868 and head abc1234.
Read a recent mac-ops ticket for the shape (for example `gh issue view 810 -R shyamsivakumar/mac-ops`) and fill every template section: Goal and why, Context, Scope and non-goals, Design fit, Blocked by, Acceptance and proof, CI, Must not cause, Data/secrets and stop conditions, Rollback, Gate, Finish. Add a `Proof command:` line.
Open each one with `ticket open --repo shyamsivakumar/strategy-replay-workbench --title "<title>" --body-file <file> --label stage:todo,type:<type>,priority:<n>`; the tool mints the key, so never type a key and never use `gh issue create`. If the source pull request's ticket title carries `Parity <Pxx>`, each piece's title is `Parity <Pxx>.<k> · <title>`, numbered from 1. If `ticket open` refuses a body or a title, fix it and retry.
After the last ticket is open, comment once on the pull request: "Superseded by #<a>, #<b>, ..." naming the new tickets, and leave the pull request open. The lane or Shyam closes it.
Start nothing, change no code, and ask no one.

```
