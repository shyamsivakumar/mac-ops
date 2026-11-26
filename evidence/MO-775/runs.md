# MO-775 runs

## Proof command

```
python3 -c "import json; m=json.load(open('reviewer_audit/manifest.json')); print(sum(1 for b in m['bundles'] if not b['expected_pass']))"
```

- Before (origin/main 04af24c1): `16`
- After (this branch): `46`

## Freeze and rerun

- Source: 135 first-gate SRW FAIL heads, two hand-coder labels (real_bug yes/no/unsure), 89 heads with at least one yes.
- Admitted: 14 heads where both coders said yes, and 16 heads where one coder said yes and the gate report names a concrete wrong behavior at file:line. 59 other yes heads were left out.
- The existing 23 bundles are unchanged byte for byte (only `bundle_count` moved from 23 to 53).
- Each diff is `git merge-base(PR base.sha, head)..head` from a scratch bare clone of the SRW GitHub repo (head sha pinned; nothing under ~/Code/strategy-replay-workbench* was touched).
- Rerun: the bundle builder ran twice from scratch (fresh `gh` reads, fresh diffs). Both runs wrote byte-identical bundle JSON; digest of the 30 input hashes `f22983945f42120b`.
- Cohort is `holdout`, `expected_pass` is false. Nothing here was scored.

## Bundles

| PR | head | how adjudicated | defect |
|---|---|---|---|
| 2240 | c5a029be3abf2c9ad2b190e2bc2732f4c843c536 | both coders yes | major R-observe-returns-unknown-the-current-paper-adapte |
| 2254 | ce9ec015e7a0b45bf4765abbbb59fe195c61321d | both coders yes | major R-route-checks-the-same-cached-snapshot-that-suppl |
| 2256 | 34793525f8ee699a1b7cdfef5d86aaec17e33f9a | both coders yes | major R-new-proof-requires-the-production-recording-day- |
| 2258 | 9686dfa70d253e6d2dc4b6169d713b0b59f69db2 | both coders yes | major R-applies-the-broker-read-limit-before-checking-th |
| 2273 | e3c72729867d1b6bd3ad5505eb316beddeb856f2 | both coders yes | major R-ticket-requires-60-and-120-seconds-the-new-r1-pr |
| 2290 | 1438e38f421caffa63e3ca72cc72ffa81c49916e | both coders yes | major R-clears-replacementpending-on-an-equal-fill-obser |
| 2293 | 4c0ec44891f58a56b12b43cf03820319cc767a76 | both coders yes | major R-can-overwrite-filledavgprice-while-retaining-the |
| 2298 | 261a0271311ba26ddeb442dfad03620a79cf809f | both coders yes | major R-ticket-admits-paper-and-live-the-head-admits-eve |
| 2301 | 3fb5d38919b1b708ecb20a9b169a5d9600c5bb0c | both coders yes | major R-broker-omits-filled-qty-adapter-returns-the-ledg |
| 2305 | edc3c6cec9e902aef1cbc0bfdf0431335295bdfc | both coders yes | major R-a-delayed-control-get-can-overwrite-a-newer-dura |
| 2314 | 0a1872fbe174ae358296789a72b7f6718d333928 | both coders yes | major R-exit-recorded-as-attempted-even-though-the-broke |
| 2319 | e27a1adb2f36ca433132f7530d39ca52fa443df6 | both coders yes | major R-suppresses-failure-to-persist-the-cleared-restor |
| 2320 | fb3acd6e93422c725e2a5b2012419581c2ed99ef | both coders yes | major R-removes-the-description-check-that-still-protect |
| 2323 | e1a10f1a50992d010e90ccc8efa1600f1e274295 | both coders yes | major R-priced-close-states-a-60-second-step-and-omits-v |
| 1608 | 136a1a8ff2044a45e79bf1c7b5386e5fd91aead9 | one coder yes + report cites file:line | major R-rotates-a-follower-s-credentials-gate-still-reso |
| 1633 | f313a8b143f064b64693118eab139b45d1e8c494 | one coder yes + report cites file:line | major R-targetexitdue-does-not-check-breakevenready |
| 1635 | c76954a3c43231ca2c3a01863c5c2d8525647803 | one coder yes + report cites file:line | major R-an-approval-for-an-expired-hold-can-reserve-its- |
| 1654 | 425c4e991e87f645b7ffa8d728b787fabf998e4d | one coder yes + report cites file:line | major R-returns-held-true-from-the-control-store-row-alo |
| 1670 | efae7694a0f711b8cd2b128ff9e68fcf7fa9dc40 | one coder yes + report cites file:line | major R-recovery-books-a-prior-day-fill-today-its-p-l-mo |
| 1676 | 841df49d302823bf487978de7f257dc04ae15233 | one coder yes + report cites file:line | major R-treats-a-request-budget-refusal-as-proof-that-th |
| 1684 | cb3cde11081349ccdbfd087a65806c742acd0cd7 | one coder yes + report cites file:line | major R-accepts-a-third-holdings-read-after-the-120-seco |
| 1709 | fe4c0ef6c090e8629510bc8806500a961742b8d8 | one coder yes + report cites file:line | major R-math-max-2-1-records-two-units-sold-when-three-s |
| 1772 | d3a881eadde42b274f65402291e32cac2f0f64eb | one coder yes + report cites file:line | major R-pairs-the-old-quantity-with-the-new-request-time |
| 1779 | acd386287b85930798367bc956f68e02bfff7b4e | one coder yes + report cites file:line | major R-reconciliation-accepts-execution-history-complet |
| 1789 | 6527ffe117faf43ffd7d7948b0833fddced2b45d | one coder yes + report cites file:line | major R-persists-a-marker-with-heartbeatatms-null-but-re |
| 1817 | fdeed352e6cce04017d2bb375f1d41b44ff0e39c | one coder yes + report cites file:line | critical R-every-imported-broker-snapshot-using-the-field-a |
| 1821 | 62531625a76a0622531840e0fa2055c088bf327f | one coder yes + report cites file:line | major R-replaydeferred-runs-the-heartbeat-and-seed-copie |
| 1849 | a62fc8d001b78348c200e7ff86d58e7ae76d8d9c | one coder yes + report cites file:line | major R-finally-clears-the-marker-even-if-the-underlying |
| 1854 | 72ab33e0d27eb9eff517f36cbefb68c40b792054 | one coder yes + report cites file:line | major R-scripted-final-fill-subtracts-two-more-the-drill |
| 1867 | 703f19f6075020abfc0dbb1a9eac85397ceb87c7 | one coder yes + report cites file:line | major R-existing-settlement-proof-regresses-from-5-5-on- |
