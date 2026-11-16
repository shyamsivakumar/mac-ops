Refs #345. Preserve run alarm identities for running threads with unknown start details. A known different run ID still retires old identities. Completed and absent threads are pruned only with a complete listing. Shutdown and exit logic unchanged.

Verification: full unittest discovery PASS (288 tests), fast check PASS, focused in-session runtime_events probe PASS for detail failure, recovery without replay, replacement, completion and disappearance. No new unit tests. Diff comment review found no added comments; bounded cleanup found no required changes. Live activation remains unverified.
