# MO-1003 scope blocker

Refs #342. Run ticket:shyamsivakumar/mac-ops#342:a1.

Prerequisite package-review is present on origin/main at eec0d2eb69227800b5f2681f28f0dfb8e2f55a4c, merged by PR #348. Issue #341 is closed.

The supported subagent preferences live in <pi-agent-dir>/subagent-manager/settings.json, not coordinator/pi/settings.json. The reviewed package docs/settings.md explicitly says other packages settings are never read. REVIEW.md identifies type models: ["deepseek/deepseek-flash"] as the supported explicit preference. The brief restricts edits to coordinator/pi/settings.json and existing installer checks. Carrying that supported preference requires an additional owned configuration file and installer mapping, outside that write set. A guessed key in the parent settings would not satisfy acceptance. The existing default API means the no-default fallback does not apply.

Stopped before implementation under the scope stop condition. Smallest re-cut: authorize the package type-preference configuration and its installer mapping, preserving parent model, guard and sandbox. Checklist meta remains off by default; its separate preference file is <agentDir>/pi-checklist.json, with /checklist settings meta as the reviewed opt-in command.

Reproduce inspection without package execution:

    git show origin/main:evidence/MO-1002/REVIEW.md
    git show origin/main:evidence/MO-1002/sources/pi-subagent-manager/package/docs/settings.md

No packages installed or executed, provider calls, background jobs, live activation, source edits or tests performed. Provides packages-pinned is not met. No PR created because implementation is blocked. Coordinator Opus gate remains outstanding.
