# MO-1008 prerequisite stop

Run: `ticket:shyamsivakumar/mac-ops#347:a1`
Date: 2026-11-16
Origin main: `c92634344017feff8b22b001bbcf690c8ac3c6aa`

`gh api repos/shyamsivakumar/mac-ops/issues/347/dependencies/blocked_by --jq 'map(.number)'` returned `[332,374,388]`. Required native dependency #346 is absent.

#346 is closed. PR #425 merged commit `7d33f57d85ba4cc5abd4079c8f63473eeb64afeb`. `git show origin/main:coordinator/pi/extensions/coordinator.ts` confirms the backlog prompt and default-enabled wake. The code prerequisite is present; the required native relationship is absent.

Stopped under the brief's prerequisite stop condition. No runbook edits, package execution, live activation, background jobs, or checks performed. No reviewer round or PR opened because implementation did not begin.

Smallest coordinator action: restore the native blocked-by relationship from #347 to #346, then resend this same bounded ticket. Provides pi-runbook remains unfulfilled.
