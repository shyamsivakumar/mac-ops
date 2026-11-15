# MO-1005 bounded inspection receipt

Run: `ticket:shyamsivakumar/mac-ops#344:a1`
Refs #344. Dependency: Refs #343.

Fetched origin/main: `a5d17cb87a9534e0455fd7a5c0b4448a4e098cfe`. Native GitHub blocked-by response identifies #343, CLOSED. watch-board exists at `coordinator/bin/coord-watch` on that revision.

Commands:
```sh
git fetch origin main
git rev-parse origin/main
git ls-tree -r --name-only origin/main coordinator/bin
gh api repos/shyamsivakumar/mac-ops/issues/344/dependencies/blocked_by
git show origin/main:coordinator/bin/coord-watch
```

Source contract inspection: `pages()` retains PR number, title, reference body and head only. No gate verdict or verdict/head association is collected. `snapshot()` emits issue stage, thread status, PR and head; it emits no lane activity or gate verdict. Therefore gate-fail cannot be implemented from the existing collected snapshot alone. The fake-input path also bypasses persisted state entirely, so restart proof requires changing that path.

Stopped before implementation: supplying and validating the missing gate/lane source contracts plus detection and restart receipts exceeds this five-minute detection-only slice. Smallest re-cut: specify the authoritative gate verdict/head and lane activity snapshot fields and permit their bounded collection, then implement detection with persistent fake-input proof.

No command execution of coordinator packages, live activation, background jobs, deployment, source edits, tests, commits or PR. Acceptance cases remain unproved. Provides watch-lanes is not established.

## Superseding coordinator authorization

Coordinator instructed continuation, waived prior stop conditions and live testing, and required the direct fast check. The implementation now reuses the existing head-keyed gate receipt and reader; the earlier stopped inspection above is historical. See review.md and replay.out for final evidence.
