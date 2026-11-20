# Replay plan: old gate brief against new gate brief

Goal: show that the new brief gives at least 10% fewer off-bar majors, misses no more real bugs, and returns the same verdict on a repeat run. The plan is not run yet. It needs one new driver script, named below.

## 1. Freeze 30 past PR heads

Source: `prompt-study/gates.json` (1163 gate replies, 273 PRs, one row per gate thread with `repo`, `pr`, `head`, `verdict`, `text`) and `prs-<repo>.json` (`mergedAt`, `state`).

Group the rows by PR, order the distinct heads by `created`, and pick three pools of 10. Take the PRs in the order given by `python3 -c` over the same data with `random.Random(20261120)` so the pick is repeatable.

| Pool | Rule | Why |
| --- | --- | --- |
| A, clean | PR has `mergedAt` and its first head got `VERDICT: PASS` (120 PRs qualify) | The new brief must not start failing good work |
| B, real bug | A head whose FAIL reply carries a major or critical that a person labels real (see section 3). The sample of 45 FAILs had 47% real, so draw from the 120+ FAIL heads and keep the first 10 that are labelled real | The new brief must still catch these |
| C, round cap | PR has 3 or more FAIL heads (86 PRs qualify). Freeze the third head, with the first two as its history | This is the pool where the round number and the prior findings matter |

Mix repos: 5 mac-ops and 5 strategy-replay-workbench per pool when the pool allows it.

For each frozen head write `replay/<repo>-<pr>-<head8>/` with:

- `meta.json`: repo, pr, issue, head, base sha (`gh api repos/<repo>/pulls/<pr> --jq .base.sha`, read only), the ticket body, the PR body, the recorded outcome and the verdict history.
- `diff.patch`: `git diff <base sha>...<head>` from a local clone, so a replay does not depend on the PR staying open.
- `proof.md`: `git show <head>:evidence/<KEY>-<issue>/check-proof.md` when the PR carries one.
- `round.json`: the `round_context` the live lane would have had. Round and previous head come from the order of heads. Prior findings come from `gate_policy.prior_findings(<text of the previous head's reply>)`. Pool A and the first head of a pool C PR are round 1.

Freezing reads GitHub (`gh api` and `git fetch`) and writes only local files.

## 2. Replay each head with the old and the new brief, 2 runs each

Both briefs come from the same function, run from two trees:

- Old: `git archive origin/main coordinator | tar -x -C <tmp>/old`, the tree before this branch.
- New: this branch.

Call `build_gate_brief(settings, repo, issue, pr, head, publisher, base, ...)` in each tree directly. `ticket gate --print-brief` cannot be used for this, because it refuses merged and closed PRs and reads live GitHub state. Pass `settings` with `"merge": "manual"` for both arms, so the ending is "Do not merge or close" and no replay can merge anything. For the new arm pass `round_info` from `round.json`. Add one fixed line to both arms: "Read `diff.patch` in <dir> instead of running `git diff`", with the same wording in both, so a closed PR and a moved base do not change the diff the reviewer sees.

Launch (4 launches per head, 120 in total):

```
export COORDQ_DIR=/private/tmp/replay-queue            # temp queue, never the live one
coordinator/bin/coordq start "$(cat <arm-run>/payload.json)" --title "replay-<arm>-<repo>-<pr>-<head8>-r<run>" --priority 900
coordinator/bin/coordq dispatch                        # with COORDQ_DIR set to the temp queue
```

`payload.json` is `{"projectId": <the repo's projectId from tickets.json>, "title": ..., "taskType": "review", "modelSelection": <the gate model, first entry of coordinator/bin/models.py review list>, "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "clientRequestId": "replay:<arm>:<repo>#<pr>:<head>:r<run>", "message": <brief>}`. Use one reviewer model for every launch (the recorded gate model was `gpt-6-astra`).

Read each reply with `t3mcp call t3_thread_read -` (the `gate_policy.reply_of` reader), and keep the last assistant message.

Can this run through coordq without touching GitHub? Partly.

- `coordq start` and `coordq dispatch` against a temp `COORDQ_DIR` never read or write the live queue, the lane ledger or any GitHub object. The launch goes to T3 only.
- The reviewer thread may still run `git fetch origin` or `gh api .../statuses` if the brief tells it to. With the `diff.patch` line above and `"merge": "manual"`, the reviewer needs no GitHub call. The "Confirm srw/agent-check success" line in the SRW brief does call GitHub, so for the replay replace the check line with the fixed text "The repo check passed on this head" in both arms.
- Needed before this can run: a driver script (about 80 lines, for example `scripts/prompt_replay.py`) that does the freezing, builds both briefs, writes the payloads and collects the replies, and a decision from Shyam to spend about 120 reviewer launches on the shared T3 quota. This plan does not write that script, since the branch adds no new files besides evidence.

## 3. Score against hand-labelled findings

1. Before any replay, a person labels every critical and major in the recorded FAIL reply of each frozen head: `real bug` (a defect a person can reproduce or read off the diff), `on-bar edge` (real but rare, the bar calls it minor) or `off-bar` (not a bug, out of scope, or already fixed). Pool B heads must carry at least one `real bug` label. Store the labels in `labels.json` keyed by `<repo>#<pr>:<head8>:<finding id>`.
2. Reduce each replay reply to its findings with `prior_findings(reply)` and map each finding to a label by file and line plus a short title match. A finding with no match goes to the labeller as a new item, blind to which arm wrote it.
3. Per head and arm, count: real bugs found, real bugs missed, majors raised that are `on-bar edge` or `off-bar` (these are the off-bar majors), verdict.

## 4. Pass criterion

All three must hold, over the 30 heads and both runs:

- Off-bar majors: the new arm raises at least 10% fewer than the old arm.
- Missed real bugs: the new arm misses no more than the old arm (count of labelled real bugs not found, summed over pools A, B and C).
- Stable verdict: for at least 27 of 30 heads (90%) the two runs of the new arm agree on PASS or FAIL. The old arm's agreement rate is reported next to it as the baseline; the new arm must not be lower.

A fail on the second criterion blocks the merge of the prompt change even when the other two pass.

## 5. Extra reads from the same data

- Pool C by round: the share of round 2 and round 3 majors that sit in lines changed since the previous head. The new brief should push this toward 100%.
- Verdict flips from FAIL to PASS on pool B and pool C against the recorded outcome, listed one by one for a person to read.
