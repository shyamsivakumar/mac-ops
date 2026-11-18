# Mac run evidence (MO-514)

The worktree cleaner on this Mac, at the head of PR #545.

- executed commit: `d6a53a9985f33c7d7896047ecebddb7fd00aea5f`
- command: `python3 scripts/worktree-cleaner/cleaner.py --dry-run --no-report`

## Dry run

- repositories scanned: 71
- worktrees scanned: 237
- categories: safe 0, needs a look 110, in use or protected 56
- eligible (would be removed): 0
- excluded repositories: 32
- held: 237

Reasons per worktree, in aggregate:

| reason | worktrees |
| --- | --- |
| detached_not_published | 17 |
| github_pr_not_closed_for_head | 104 |
| github_pr_open | 13 |
| main_checkout | 71 |
| process_cwd_inside | 7 |
| remote_commit_unverified | 153 |
| t3_thread_unfinished | 41 |
| worktree_dirty | 79 |
| worktree_missing_or_prunable | 11 |
| worktree_outside_scope | 84 |
| worktree_status_unknown | 1 |

Every worktree that was scanned, with the reason it is held:

| path | branch | head | reasons |
| --- | --- | --- | --- |
| `/Users/shyamsivakumar/.codex/worktrees/4317/fantasy-football-toolkit` | codex/m13-lineage-ledger-backlog | 43d3b397f78a | worktree_outside_scope |
| `/Users/shyamsivakumar/.codex/worktrees/7142/fantasy-football-toolkit` | detached | f343e9584585 | worktree_outside_scope |
| `/Users/shyamsivakumar/.codex/worktrees/anti-slop-backfill-web` | codex/anti-slop-baseline-backfill-web | 10b17d75ab4f | worktree_outside_scope |
| `/Users/shyamsivakumar/.codex/worktrees/b582/fantasy-football-toolkit` | codex/matrix-auction-receipt-doc-contract-backlog | b90016cbef67 | worktree_outside_scope |
| `/Users/shyamsivakumar/.local/share/mac-ops-install` | detached | 842a1969421a | worktree_outside_scope |
| `/Users/shyamsivakumar/.local/state/llmwiki-review/worktrees/review-2026-11-12-0031` | wiki/review-2026-11-12-0031 | 4a78acda7c46 | worktree_outside_scope |
| `/Users/shyamsivakumar/.local/state/llmwiki-review/worktrees/review-2026-11-12-0630` | wiki/review-2026-11-12-0630 | 1d0e89e4d46a | worktree_outside_scope |
| `/Users/shyamsivakumar/.t3/worktrees/CineJar/t3-6ada78dc-e92e6da145a19275` | t3/accessible-error-retry-button | 77b5b848487c | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-59697cc6-2313540acd254d38` | t3/value-diff-impact-plan | 45ec9f04a10e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-817e6343-d86ebae2e6f871ab` | t3/single-agent-fix-benchmark | 45ec9f04a10e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f2-cas-conflict-A` | detached | c01aa05c5484 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f2-cas-conflict-B-fix` | detached | c01aa05c5484 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f2-cas-conflict-B-invest` | detached | c01aa05c5484 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f2-heartbeat-recovery-A` | detached | 3ea2fe3a4e99 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f2-heartbeat-recovery-B-fix` | detached | 3ea2fe3a4e99 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f2-heartbeat-recovery-B-invest` | detached | 3ea2fe3a4e99 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f3-recovery-fence-A` | detached | 8ff0ec226371 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f3-recovery-fence-B-fix` | detached | 8ff0ec226371 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-be78b59e-21cfcf58d384d21f/evals/fix-bench/state/runs/f3-recovery-fence-B-invest` | detached | 8ff0ec226371 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-bfcb773a-ae87f52b04435d87` | t3/workflow-crash-investigation | 45ec9f04a10e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-crn-18-moved` | t3/crn-18-moved | 45ec9f04a10e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/cairn/t3-crn-19-moved` | t3/crn-19-moved | 45ec9f04a10e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/catalogue/t3-7ecf0b27-68ce9011a4aa60bc` | t3/m4-device-evidence-4 | 118839b60162 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/catalogue/t3-7f8bd63e-d45ae621bc94803e` | t3/wardrobe-import-pilot-evidence | 5e6137524a7d | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/catalogue/t3-a1e4baf0-952b4c4d4d11f512` | t3/m4-device-evidence-3 | 118839b60162 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-1bd9b9e6-95c92394691f3ea2` | t3/invite-redemption-audit-slice | 10bad28f38ba | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-6cc00be6-418aeee9357c5436` | detached | 0743cd55c35f | detached_not_published, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-a248118e-806b5489338cca83` | t3/fix-pr-builder-check-line | 74c4d8977b33 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_missing_or_prunable |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-con-102-dry-run-25642a6bcda8ce92` | t3/con-102-dry-run | 0743cd55c35f | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-con-102-grants-331bb1e4deb7fd9e` | t3/con-102-grants | 9f58ce770167 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-con-105-rebase` | con-15-area-concern-workspace-invariant | 99035592231a | github_pr_open, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-con-14-fix-81bd08089d88164d` | t3/con-14-fix | 5f259a1e24a1 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-e0f553f3-52fdfde222f25372` | t3/expose-build-commit-health | b15aa216a258 | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-ning-13-redesign-bui-5e3330407d52e635` | t3/ning-13-redesign-build | 2ac9adf0066c | remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-terrane-landing-memo-20e2c5ce95593d80` | t3/terrane-landing-memo-redesign-6b | 68811951a13c | remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-terrane-landing-memo-be94dbf088947796` | t3/terrane-landing-memo-redesign-5 | 3ed7a9a7e636 | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/concerning/t3-terrane-landing-memo-e7c37d3584806e49` | t3/terrane-landing-memo-redesign-6 | 1e68c8a2934e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/ffbt-9-agentic-ci-check-before-merge-4926c6` | work/ffbt-9-agentic-ci | 6bd621da31f9 | remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-03f3a441-0e0f8e433297446d` | t3/verify-live-draft-state-1 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-0fb6b1f6-f036a38ff8a4e4e8` | t3/shared-decision-evidence-10 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-1039c7d5-87ae189ab0c83e46` | t3/release-evidence-gates | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-1336458f-799f86f3383f7095` | t3/shared-decision-evidence-13 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-147fa991-7c82f265f5207664` | t3/dynasty-parity-audit | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-2acf6dbc-7512c6fe64f32b1f` | t3/audit-gw7-generation-receipts | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-3211a72a-208f6c7eebf6532a` | t3/release-evidence-layers | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-398b227b-55ae19d6af22a49b` | t3/audit-gw7-frozen-generation | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-4282e3b6-fbc6831ca10a8ac6` | t3/shared-decision-evidence-19 | 063a06427acc | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-47ece717-5276ab9cc90edfed` | t3/shared-decision-evidence-15 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-561053ca-d0b1e84d70d5d02c` | t3/shared-decision-evidence-2 | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-589593a3-22475e649a814bea` | evidence/ffbt-23-fantrax-source-matrix | 89cd352f58e3 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-5c5f339f-b962508a3bd469a8` | t3/shared-decision-evidence-9 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-649a991e-1960a76eb95638bc` | t3/459-lineup-robustness | fa9dec0001c3 | remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-77de8189-9522230b5fee5acc` | t3/shared-decision-evidence-7 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-782ab740-aecb4379c55601c2` | t3/dynasty-parity-design-2 | 6d4611d5a490 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-84bd2aa6-5157146a4e04615d` | t3/shared-decision-evidence-20 | c99a9a98cf36 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-89bf032c-faa726a184fa1731` | t3/gw7-frozen-generation-rca | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-8d81505d-984b2d0ab9745c28` | t3/shared-decision-evidence | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-9d26a862-8c49ffc8d9d225ba` | work/ffbt-35-approved-news-source-inventory | c4220408fbb6 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-a5af6f6e-9f7dcef81ccaf344` | t3/shared-decision-evidence-1 | 1ef81138241e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-a80eb391-2f1ff39df63a1ae4` | t3/shared-decision-evidence-21 | 90b36e555db4 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-ab1a9783-edd6ced09d9eac6e` | t3/shared-decision-evidence-12 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-abe2a11f-d34173bddc2dc7b2` | t3/acquisition-evidence-row | 2e9ac9ad6b00 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-ac245719-30eb9a47020bcd65` | codex/ffbt-16-nominee-guidance | a1b526bc4163 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-aeb91a67-535c50b9ab31e0b6` | t3/auction-decision-evidence-adapter | 7e598d3c229e | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-c233c8d8-3e4a3d0dabb968a1` | ffbt23-a2-merge | b47588662c58 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-c6264572-c228ce2f7e388ae1` | t3/shared-decision-evidence-4 | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-c65ecb48-1996d363d65656d7` | t3/shared-decision-evidence-6 | d1380f12873b | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-cf28b097-da4181d8c3c03d15` | t3/dynasty-parity-design-3 | 6d4611d5a490 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-d3a0f6aa-fcae78767225e0b5` | t3/audit-gw7-generation-receipts-2 | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-d6cdef0c-a7b9dfab130f1675` | t3/shared-decision-evidence-17 | 0dd492e5e98f | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-d6e784bc-a3ff6e88b978e272` | t3/pr472-generation-fix | fb9a69b0359d | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-e160c15e-324e92ab58b434b9` | t3/audit-gw7-generation-receipts-1 | 799a8258b67a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-f3dd13ed-5681fe3323a05780` | t3/dynasty-parity-triage | 2ea2948765ea | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/fantasy-football-toolkit/t3-fda94c61-4f3e8d8bcec6a599` | t3/football-news-source-contracts | 0322ba5506f5 | remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/llmwiki/t3-49d25966-69bf5241e76e386b` | docs/pencil-paper-mcp-20261116 | bd0ae1399a44 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/llmwiki/t3-5843bb0b-ebd4df4f2753c9a2` | detached | 21118d94f331 | detached_not_published, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/llmwiki/t3-8dea0117-b2cf0945edd0e418` | fix/launchd-bootstrap-loaded-check | 3cb9045719c9 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/llmwiki/t3-91122478-c58df0f5c4bd7ad9` | t3/explain-refactoring-design-debt-pages | b3e42f8a69ad | github_pr_open, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-0b52757a-92a5e3a85418e130` | t3/traces-trial-findings | 99b14ecd94f8 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-190b68f0-118b49042f0f6e1c` | t3/overnight-pr-state-actions | 88217fd4b647 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-22350cfe-02533d768be081e9` | t3/mo245-shift-health | ac247e18ec78 | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-2767e585-3aaf4aae17942d16` | t3/worktree-cleaner-auto-archive | d6a53a9985f3 | github_pr_open, process_cwd_inside, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-3893369a-fd3a15a73c0995bb` | t3/astra-reviewer-chain-openai-api | 68479d7b94c4 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-3893415e-a05be649c7b45064` | t3/overnight-stall-sweep-alert | a224366c8255 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-3b3f29fb-d559100edfc2f01a` | t3/lane-queue-dedupe-reservations | e5bf969d0332 | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-4c50e113-b71e72ea5e0cba10` | t3/normalize-ticket-section-headings | a19b8a09708a | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-58283951-ecb9ff8b5480bca3` | t3/overnight-selftest-routing | ddb69591422d | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-5c6cfdb3-0b4876575ac51cff` | t3/coord-watch-full-check | 529c09b17d54 | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-5cbd9acd-0e1ae499158a5539` | detached | d8697aa57e22 | detached_not_published, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-5da9caa8-83326c328876ff49` | t3/mo-1083-ds-continue | f5ac2a6b5a5a | github_pr_not_closed_for_head, process_cwd_inside, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-63e68ccf-a7a81e80537cb8cf` | t3/merge-520-496 | fbecac3930da | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-688c5e35-095a9dbc4164a320` | t3/selftest-eval-five-watchdog | f118e2d3e253 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-68e03d08-a6f67d35e6602587` | t3/overnight-merge-progress | 4674790ddfd9 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-8323093c-7304dfba01517719` | t3/ticket-close-proof-evaluator | c948fdd300c9 | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-865951de-e62ce126f0e194c6` | t3/coord-watch-runtime-alarms | 82e1398a150b | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-86fb60cc-77f3858e291ab650` | t3/gpt-6-review-glm-build | 3194ec762307 | remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-8df2d86a-b4a891cb2200aaad` | t3/hourly-fixture-selftest | e6fefb0726ee | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-96fe6833-f2c2c5654a518719` | t3/overnight-builder-budgets | f0f25b0705b8 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-9a54a106-ab04fa6a87dcbbd2` | t3/overnight-pr-actions | 4f0fa763ca51 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-a21e3469-1d212e1c95923be1` | t3/enforce-agent-deny-rules | 95f8b8d34809 | github_pr_open, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-af05d4d4-92a8fafc3dde265b` | t3/prompt-question-quick-answers | 9dabf45d5749 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-b0403464-2d79187186b26f5f` | t3/coordinator-tick-call-timeouts | 5547e96601ad | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-d0fd643e-c890630b5592eb54` | t3/gate-main-fast-forward | b5db52b67228 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-d3c05f6b-0816e79cd3256c91` | t3/prompt-pr-no-auto-merge | 9f2d7edf6c65 | github_pr_open, process_cwd_inside, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-d55e849b-7ac34c278c502d06` | mo-1060-finish | ce79295f57ec | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-e05fc9b2-bbe83cb200cb4954` | t3/atomic-ticket-stage-labels | 61a6355e4f5b | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-ed0cc1ab-dd469dc6a2dc50a9` | t3/heavy-admit-ios-builds-16gb | bbfca75ef74c | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-mo-1072-heavy-headro-7047753fa31e514d` | t3/mo-1072-heavy-headroom | 8cc4e7b565ec | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-mo-1081-ds-c2a8b679bfa1cfe2` | t3/mo-1081-ds | ab1678b3e6de | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-mo-1082-builder-fall-f25933ab4a05df56` | t3/mo-1082-builder-fallback | de52a7d5de6a | github_pr_open, process_cwd_inside, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-mo-1083-ds-f14d3e93d7c4c72c` | t3/mo-1083-ds | a07ebdb9792d | github_pr_open, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-mo-1084-ds-e622750ab7149819` | t3/mo-1084-ds | 607c9120c611 | github_pr_open, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-mo-185-cockpit-t3-efa57bdfd7448ec4` | t3/mo-185-cockpit-t3 | 9423ca179385 | remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/mac-ops/t3-mo-270-rebase-pr311-fc38c73af7eb1e6b` | t3/mo-270-rebase-pr311 | 5ce66ce63dab | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/openscan/t3-25f5512f-9e45f786321572b2` | t3/opn-14-export-pdf | 7ae819aaaa31 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/openscan/t3-37df92f0-7e757cf1e03538c8` | t3/opn-13-preview-multipage-pdf | 0767a2f1d9fe | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/openscan/t3-64818e9c-78075469df32f58e` | t3/unsigned-iphone-simulator-app | 8555a0ae4601 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/openscan/t3-7bff16b6-58d8c9b3dbb0b071` | t3/opn-11-unsigned-ios-simulator-app | fd2bb3659022 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/openscan/t3-af517c91-ac9b4d25dfea9d30` | t3/unsigned-iphone-simulator-app-1 | f5624f164c75 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/openscan/t3-c03096a0-47d8a249e6d3e037` | t3/opn-12-import-page-images | 13b69e6d495e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/openscan/t3-c99986dc-a0c075a880e9441a` | t3/preview-assembled-pdf | 66b0399d8c70 | remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/qabot/t3-ba5b1c68-a2e22c8c783e520f` | t3/exclude-inert-sweep-text | 5958439098b1 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/qabot/t3-e5e25b5d-22e8b6b5ad80e0bb` | t3/fence-pr-metadata | 8804c1db8419 | remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-02c2b9b9-1f524b3a48903c86` | t3/privacy-deletion-instructions-match-settings | 53bedbe2567b | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-1373d7af-0f2d184c1a55345c` | t3/route-release-checks-heavy | 963a4d37fb95 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-22272ce0-19625a477e824c28` | t3/rcp-22-repeated-reauth-notice | 8df596263154 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-2c10b1cd-dbb7b86338b6a474` | detached | 54a9965e7753 | detached_not_published, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-64e705db-3a51f68531d2c1c8` | t3/rcp-25-mock-simulator-smoke-receipt | dc7fd1badd37 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-71069245-6b3af1357a961ea9` | t3/route-release-checks-through-heavy-1 | e709a34f10bd | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-971a7756-f47be557103e5a2c` | t3/route-release-checks-through-heavy | 963a4d37fb95 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-9d177d0e-0d1ecbc6662b0e75` | t3/apple-reauth-deletion-notice | e103f2d2acb9 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-a5a0e432-b7597885b570e3ab` | t3/route-release-checks-through-heavy-2 | 2c1ee44babdf | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-c03e0bf1-f0d082958543d933` | t3/privacy-deletion-settings-alignment | 54a9965e7753 | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-c08b06d6-173ce4972eff2cbf` | feature/RCP-25-mock-simulator-smoke-receipt | bb0c61ac4a95 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/recoup/t3-d2c42691-9b44a5ded5b0ba39` | t3/verify-bank-health-before-reconnected | e98068351f5c | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/scripture-scroll/t3-1d3e4737-e19ed720cc240508` | t3/spaced-repetition-verse-reviews | f21965ebcd25 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/scripture-scroll/t3-7f419b5c-c127d3801a8db27f` | t3/pseudo-locale-ui-screenshot-audit | 96a1c2eec007 | process_cwd_inside, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/scripture-scroll/t3-8071ca57-d59e2872e1001986` | t3/pseudo-locale-screenshot-audit | e71e3a5e08f2 | github_pr_not_closed_for_head, process_cwd_inside, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/scripture-scroll/t3-84a89d4e-f68154b77d50b9f4` | t3/pseudo-locale-guard-fixes | e71e3a5e08f2 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/amp-tnr-22` | amp/tnr-22 | 3a554539735a | github_pr_open, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/amp-tnr-23` | amp/tnr-23 | b74e4613a1b1 | github_pr_open, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/amp-tnr-24` | amp/tnr-24 | 44de6a69bd53 | github_pr_open, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/amp-tnr-25` | amp/tnr-25 | 1ff34d75f249 | github_pr_open, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/amp-tnr-26` | amp/tnr-26 | 7ef21ce6c16c | github_pr_open, remote_commit_unverified, t3_thread_unfinished |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/check-bf351e7` | detached | bf351e7c9268 | detached_not_published, process_cwd_inside, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-19a4b3ae-9c56076728b57709` | detached | 44de6a69bd53 | detached_not_published, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-1f15de68-4bdf01be92c40066` | t3/reject-blank-unsupported-source-addresses | 0a2adc79b37e | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-4723d9c0-9045c0b25989667f` | t3/tnr-23-report-file-import-errors | 9da30d88a381 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-6312c1bc-9beaf0a06abaa888` | t3/show-playback-failure-retry | f250fc704e13 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-8a08a700-d6734fd95741a5a6` | t3/show-failed-playback-retry | 0a2adc79b37e | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-907ce842-64eed77d4d94211a` | detached | e7b8cd6d3fcc | detached_not_published, remote_commit_unverified |
| `/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-f4bdd273-f8a5501f45404698` | t3/report-file-import-errors | a091d4f28e2b | github_pr_not_closed_for_head, remote_commit_unverified, t3_thread_unfinished, worktree_dirty |
| `/Users/shyamsivakumar/Code/.worktrees/ffbt-412` | pr412-check | 6bd621da31f9 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/Code/.worktrees/mac-ops/herdr-act-log` | herdr/act-log | c73c38c722a4 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/Code/.worktrees/mac-ops/herdr-quick-answers` | herdr/quick-answers | fb40d8cbb650 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/Users/shyamsivakumar/Code/_archive/codex-automation-control-heartbeat-quality` | automation/heartbeat-quality-review | 3d70e0ccdd42 | worktree_outside_scope |
| `/Users/shyamsivakumar/Code/_archive/codex-automation-control-task-local-heartbeats` | automation/task-local-heartbeats | 1807b9075e90 | worktree_outside_scope |
| `/Users/shyamsivakumar/Code/mac-ops/.claude/worktrees/drift-warning` | work/drift-warning-2026-11-06 | 2442a6947965 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/Code/mac-ops/.claude/worktrees/hub-last-error` | work/hub-last-error-2026-11-06 | 8a008c8c6b44 | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/Code/mac-ops/.claude/worktrees/port-base` | work/port-base-reaches-shell-2026-11-06 | 23999cde393a | github_pr_not_closed_for_head, remote_commit_unverified, worktree_dirty |
| `/Users/shyamsivakumar/Code/mac-ops/.empryo/tmp/tabs/5ac2e513-9d4e-4390-a112-aa517d650f56/mo181` | detached | 37bdada62bd3 | worktree_outside_scope |
| `/private/tmp/fb-c1` | detached | c01aa05c5484 | detached_not_published, remote_commit_unverified, worktree_missing_or_prunable, worktree_status_unknown |
| `/private/tmp/mo1022-fix` | mo1022-fix | 9695d522c417 | github_pr_not_closed_for_head, remote_commit_unverified |
| `/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/cinejar-pre-push.LMrabY` | detached | 77b5b848487c | worktree_outside_scope |
| `/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/manifestfix` | fix/ffbt-32-build-integrity-manifest | 974857c581fb | worktree_outside_scope |
| `/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tnr26-rebase` | detached | e7b8cd6d3fcc | worktree_outside_scope |

## Real run

`python3 scripts/worktree-cleaner/cleaner.py --apply --no-report`

- removed: 2
- categories after the run: safe 0, needs a look 110, in use or protected 56, removed 2
- eligible after the run: 0
- prune after the run: ok for `/Users/shyamsivakumar/Code/concerning`

The append-only log `worktree-cleaner.log` recorded one `removal_attempted`
and one `removed` entry per worktree, each with the repo, the path, the
branch, the head and the rule that authorised the removal:

| path | branch | head | eligibility rule | pull request |
| --- | --- | --- | --- | --- |
| `~/.t3/worktrees/concerning/t3-183d70ea-e8dc1b09f1a23b41` | detached | `ee144cdce81684d1ea23e7a0ae19f3f399fdd35b` | `merged_or_closed_pull_request` | https://github.com/digitized/Concerning/pull/98 |
| `~/.t3/worktrees/concerning/t3-con-106-rebase` | `con-16-invite-atomic-expiry` | `7f3aec405992bb8f5d346301e07ce0eb5a69283f` | `merged_or_closed_pull_request` | https://github.com/digitized/Concerning/pull/106 |

## GitHub confirmation for every removed head

The cleaner only authorises a removal after the GitHub API confirms that
the exact head commit exists on GitHub and that the pull request for it is
merged or closed. Both removals above passed that check during the run,
which is why their pull requests are named in the log.

A separate manual re-check of the same two commits with
`gh api repos/digitized/Concerning/commits/<head>` was refused at the time
of writing with `403 API rate limit exceeded`, so the confirmation above
is the one the run itself made and the pull request links are given for
a manual check.

Every branch of the removed worktrees still exists locally, and no remote
ref changed.

## The removal log on this Mac

The installed cleaner writes the same record to
`~/.local/state/mac-ops/worktree-cleaner.log`.

Device, handset and live-service testing was waived by Shyam on 2026-11-14
("no testing is needed"), so no device or live-service case was run for this
change. The runs above are the local cleaner on this Mac.
