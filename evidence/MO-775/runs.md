# MO-775 runs

## Proof command

```
python3 -c "import json; m=json.load(open('reviewer_audit/manifest.json')); print(sum(1 for b in m['bundles'] if not b['expected_pass']))"
```

- Before (origin/main 04af24c1): `16`
- After (this branch): `42`

## How the heads were chosen

- Pool: 135 first-gate SRW FAIL heads, two hand-coded real_bug labels, 89 heads with at least one yes.
- Rule: both coders yes, or one coder yes plus a concrete wrong behavior at a file:line that sits inside the bundle's own diff, where a gate reading only the bundle could find it.
- Dropped after the Fable review: 2240, 1608 (need code outside the diff), 1779 (unwired, no file:line), 2298 (spec disagreement), and by the same test 2256 (the divergence predates the diff), 2305, 1633, 1670 (the defect lives in code the diff does not show). That leaves 22 of the first 30.
- Added from the unread one-yes pool with the same test: 2463, 2379, 2170, 2353. Total new: 26, so 16 + 26 = 42. The other 55 yes heads were screened by automated file:line-in-hunk check only and not admitted.

## What each bundle carries

- `description`: the ticket body (the issue the PR refs, rebuilt from GitHub edit history as of the gate time) plus the PR title and body as of the gate time. Where every recorded edit is later than the gate, the oldest recorded edit is used; the Notes column says so.
- `saved_proof`: the builder's own `evidence/SRW-<ticket>/check-proof.md` at the head when the PR has one (3 of 26), otherwise empty. The gate FAIL report is not in the bundle's prompt text. It survives only as `saved_finding_subjects` and `saved_requirement_ids`, which `shadow.py` does not print.
- `adjudicated_defects`: one defect, the gate finding that matches the coder's quote, with the id the scorer derives from that finding (`requirement_ids_for_finding`: the regex rules, else `REQ-OTHER-<slug>`).
- Replaying the original FAIL report's finding subjects on its own bundle through `compute_bundle_metrics` gives defect recall 1.0 for all 26 (column Recall). A generic subject gives 0.0 for all 26.
- Diffs are `git merge-base(PR base.sha, head)..head` from a scratch bare clone of the SRW GitHub repo.
- The builder ran twice from scratch; both runs wrote byte-identical bundles and notes. `review_round` is 1 on every bundle: neither fails.json nor the journal records the gate round of the FAIL head.

## Bundles

| PR | head | ticket | adjudicated by | Recall | Notes |
|---|---|---|---|---|---|
| 2254 | ce9ec015e7a0b45bf4765abbbb59fe195c61321d | #1813 | both coders yes | 1.0 | ticket: oldest recorded edit (all 2 edits are after the gate); PR body: oldest recorded edit (all 5 edits are after the gate); own proof: none |
| 2258 | 9686dfa70d253e6d2dc4b6169d713b0b59f69db2 | #1845 | both coders yes | 1.0 | ticket: oldest recorded edit (all 2 edits are after the gate); PR body: oldest recorded edit (all 5 edits are after the gate); own proof: none |
| 2273 | e3c72729867d1b6bd3ad5505eb316beddeb856f2 | #1846 | both coders yes | 1.0 | ticket: never edited; PR body: edit 6 of 12 as of gate time; 6 later edits; own proof: none |
| 2290 | 1438e38f421caffa63e3ca72cc72ffa81c49916e | #2282 | both coders yes | 1.0 | ticket: oldest recorded edit (all 2 edits are after the gate); PR body: edit 4 of 6 as of gate time; 2 later edits; own proof: none |
| 2293 | 4c0ec44891f58a56b12b43cf03820319cc767a76 | #2177 | both coders yes | 1.0 | ticket: never edited; PR body: edit 2 of 10 as of gate time; 8 later edits; own proof: none |
| 2301 | 3fb5d38919b1b708ecb20a9b169a5d9600c5bb0c | #2283 | both coders yes | 1.0 | ticket: oldest recorded edit (all 2 edits are after the gate); PR body: oldest recorded edit (all 11 edits are after the gate); own proof: none |
| 2314 | 0a1872fbe174ae358296789a72b7f6718d333928 | #1689 | both coders yes | 1.0 | ticket: never edited; PR body: edit 2 of 6 as of gate time; 4 later edits; own proof: none |
| 2319 | e27a1adb2f36ca433132f7530d39ca52fa443df6 | #2247 | both coders yes | 1.0 | ticket: never edited; PR body: edit 2 of 6 as of gate time; 4 later edits; own proof: none |
| 2320 | fb3acd6e93422c725e2a5b2012419581c2ed99ef | #2308 | both coders yes | 1.0 | ticket: oldest recorded edit (all 3 edits are after the gate); PR body: edit 2 of 17 as of gate time; 15 later edits; own proof: none |
| 2323 | e1a10f1a50992d010e90ccc8efa1600f1e274295 | #2312 | both coders yes | 1.0 | ticket: oldest recorded edit (all 2 edits are after the gate); PR body: edit 2 of 11 as of gate time; 9 later edits; own proof: none |
| 1635 | c76954a3c43231ca2c3a01863c5c2d8525647803 | #1617 | one coder yes + file:line in diff | 1.0 | ticket: edit 2 of 3 as of gate time; 1 later edits; PR body: edit 2 of 3 as of gate time; 1 later edits; own proof: none |
| 1654 | 425c4e991e87f645b7ffa8d728b787fabf998e4d | #1650 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 2 of 6 as of gate time; 4 later edits; own proof: none |
| 1676 | 841df49d302823bf487978de7f257dc04ae15233 | #1620 | one coder yes + file:line in diff | 1.0 | ticket: edit 2 of 3 as of gate time; 1 later edits; PR body: edit 2 of 7 as of gate time; 5 later edits; own proof: none |
| 1684 | cb3cde11081349ccdbfd087a65806c742acd0cd7 | #1468 | one coder yes + file:line in diff | 1.0 | ticket: edit 6 of 6 as of gate time; 0 later edits; PR body: edit 2 of 7 as of gate time; 5 later edits; own proof: yes |
| 1709 | fe4c0ef6c090e8629510bc8806500a961742b8d8 | #1686 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 2 of 8 as of gate time; 6 later edits; own proof: none |
| 1772 | d3a881eadde42b274f65402291e32cac2f0f64eb | #1687 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 2 of 5 as of gate time; 3 later edits; own proof: yes |
| 1789 | 6527ffe117faf43ffd7d7948b0833fddced2b45d | #1736 | one coder yes + file:line in diff | 1.0 | ticket: edit 2 of 2 as of gate time; 0 later edits; PR body: oldest recorded edit (all 2 edits are after the gate); own proof: none |
| 1817 | fdeed352e6cce04017d2bb375f1d41b44ff0e39c | #1794 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 2 of 3 as of gate time; 1 later edits; own proof: none |
| 1821 | 62531625a76a0622531840e0fa2055c088bf327f | #1735 | one coder yes + file:line in diff | 1.0 | ticket: edit 2 of 2 as of gate time; 0 later edits; PR body: edit 2 of 8 as of gate time; 6 later edits; own proof: none |
| 1849 | a62fc8d001b78348c200e7ff86d58e7ae76d8d9c | #1784 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 4 of 12 as of gate time; 8 later edits; own proof: none |
| 1854 | 72ab33e0d27eb9eff517f36cbefb68c40b792054 | #1795 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 2 of 3 as of gate time; 1 later edits; own proof: yes |
| 1867 | 703f19f6075020abfc0dbb1a9eac85397ceb87c7 | #1688 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 2 of 15 as of gate time; 13 later edits; own proof: none |
| 2463 | 891caeff71db2a90c93ea3caa9683a486793e20c | #2460 | one coder yes + file:line in diff | 1.0 | ticket: edit 2 of 2 as of gate time; 0 later edits; PR body: edit 3 of 8 as of gate time; 5 later edits; own proof: none |
| 2379 | 3f2907a82da3ab9d6fe894528636ead5075d09df | #2375 | one coder yes + file:line in diff | 1.0 | ticket: oldest recorded edit (all 2 edits are after the gate); PR body: oldest recorded edit (all 2 edits are after the gate); own proof: none |
| 2170 | 25a928b52771e112754446c4b0c84b7225a56dcc | #2143 | one coder yes + file:line in diff | 1.0 | ticket: never edited; PR body: edit 3 of 4 as of gate time; 1 later edits; own proof: none |
| 2353 | e45f09604e93146a067e1396ddd0db863f6b1eaa | #2318 | one coder yes + file:line in diff | 1.0 | ticket: oldest recorded edit (all 4 edits are after the gate); PR body: oldest recorded edit (all 6 edits are after the gate); own proof: none |
