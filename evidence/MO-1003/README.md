# Pinned coordinator packages

Refs #342. Continuation authorizes additional owned package configuration and installer mappings; supersedes INITIAL-SCOPE-NOTE.md.

Pins: pi-background-monitor 1.0.1, pi-checklist 3.3.0, pi-subagent-manager 1.9.0. Existing installer carries settings and seven additional files. Six bundled role YAML overlays set models to deepseek/deepseek-flash; pick-first-scoped uses that preference and enabledModels includes it. Parent model, guard and sandbox remain unchanged. Custom/project roles and restored definitions may override these defaults. Provider availability is not verified.

Supported contract: evidence/MO-1002 package docs/custom-agents.md and docs/settings.md, runtime.ts:242-262. Checklist meta remains off by default; explicit opt-in is /checklist settings meta, persisted separately in agentDir/pi-checklist.json. No automatic metadata enablement or new scheduler.

Prerequisite review merged at eec0d2eb69227800b5f2681f28f0dfb8e2f55a4c; native blocked-by #341 confirmed through GitHub dependencies API. Provides packages-pinned remains pending merge.

Verification: timeout 300 python3 scripts/mac_ops_fast_check.py passed, including 44 existing installer tests. Temporary HOME receipt verifies existing plan/atomic_write mapping byte equality and pins; resolve TemporaryDirectory path before invoking atomic_write to avoid /var symlink refusal. Reproduce with tempfile.TemporaryDirectory, Path(t).resolve(), install_coordinator.plan(Path.cwd(), home), atomic_write(target, src.read_bytes(), mode), and assert target.read_bytes() == src.read_bytes() for each coordinator/pi source.

Live/device/provider testing waived by coordinator. No live activation or package execution. No tests modified or added. Diff cleanup and comment review found no additional changes needed. Runtime extension guard gaps remain as documented in MO-1002; installation configuration does not close those gaps.
