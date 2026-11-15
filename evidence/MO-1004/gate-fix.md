# PR #350 gate fix

The gate rejected head 8b57d802f788020e0f7c7fe9ffb6ef3d8bcd7d53 because append mode concatenated state documents on the second cycle and prevented the third BOARD event.

The state descriptor now uses O_RDWR | O_CREAT, mode 0600 for new files, wrapped in r+ text mode. It has neither O_APPEND nor O_TRUNC. The existing exclusive lock is acquired before the read and held through seek, replacement write and truncate. No queue input or live installation changes.

The existing offline command proof now runs three actual executable cycles. After each it parses the entire persisted file with json.loads and checks that persisted items match that cycle's BOARD items. It also confirms stable output, two GitHub calls total through cache reuse and unchanged queue bytes. Command: `timeout 300 python3 evidence/MO-1004/collect-proof.py`. Result: PASS; receipt collect-proof.out.

Command: `timeout 300 python3 scripts/mac_ops_fast_check.py`. Result: PASS, including syntax and 44 selected existing tests; receipt gate-fix-fast-check.log. README.md section "Check a task" names this check; no separate full-suite command was found in current repository docs. This is selected-check coverage, not a claim of a full-suite run. No existing test or check was weakened.

Device, handset, owner and live-service cases were waived by Shyam's instruction, not failed, and were not run. No merge or activation was attempted. Existing state files already containing concatenated documents are not automatically repaired; the fix prevents recurrence for valid or newly created state. The collector was never activated by this ticket.

Read-only review of this fix found no further critical or major issue: open does not truncate before locking, subsequent writes replace the prior document, and json.loads in the proof detects trailing documents. Earlier review notes describe the original two-cycle proof; this three-cycle receipt supersedes that coverage statement.
