# Pinned coordinator packages

Refs #342. Continuation authorizes additional owned package configuration and installer mappings; supersedes INITIAL-SCOPE-NOTE.md.

Pins: pi-background-monitor 1.0.1, pi-checklist 3.3.0, pi-subagent-manager 1.9.0. Existing installer carries settings and seven additional files. Six bundled role YAML overlays set models to deepseek/deepseek-flash; pick-first-scoped uses that preference and enabledModels includes it. Parent model, guard and sandbox remain unchanged. Custom/project roles and restored definitions may override these defaults. Provider availability is not verified.

Supported contract: evidence/MO-1002 package docs/custom-agents.md and docs/settings.md, runtime.ts:242-262. Checklist meta remains off by default; explicit opt-in is /checklist settings meta, persisted separately in agentDir/pi-checklist.json. No automatic metadata enablement or new scheduler.

Prerequisite review merged at eec0d2eb69227800b5f2681f28f0dfb8e2f55a4c; native blocked-by #341 confirmed through GitHub dependencies API. Provides packages-pinned remains pending merge.

Verification: timeout 300 python3 scripts/mac_ops_fast_check.py passed, including 44 existing installer tests. Temporary HOME receipt verifies existing plan/atomic_write mapping byte equality and pins; resolve TemporaryDirectory path before invoking atomic_write to avoid /var symlink refusal. Reproduce with tempfile.TemporaryDirectory, Path(t).resolve(), install_coordinator.plan(Path.cwd(), home), atomic_write(target, src.read_bytes(), mode), and assert target.read_bytes() == src.read_bytes() for each coordinator/pi source.

Live/device/provider testing waived by coordinator. No live activation or package execution. No tests modified or added. Diff cleanup and comment review found no additional changes needed. Runtime extension guard gaps remain as documented in MO-1002; installation configuration does not close those gaps.

Read-only reviewer round: corrected inherited broad tool filtering to allowed, using bundled explicit role allow lists. Unresolved: monitor custom tools expose execution/control outside existing coordinator guard. This PR is configuration only and must not be activated until the coordinator gate accepts or addresses that integration gap. Earlier scope note is historical and superseded.

## Gate repair

The monitor guard finding is resolved at the existing tool_call boundary. All bgmon_ names fail closed except bgmon_inspect, bgmon_watch (subscription management only), and bgmon_events with action list. bgmon_start, every bgmon_control action, event clearing, missing event actions and unknown monitor tools are blocked before execution. Subscription management changes observation state but cannot start/stop jobs or delete retained history; existing lane actions remain responsible for remediation. This supersedes the unresolved monitor finding above. It does not sandbox trusted extension internals or interactive user commands.

Reproduce: timeout 300 bun evidence/MO-1003/guard-probe.ts. The retained fake-Pi integration probe invokes the actual registered tool_call handler, without importing the package or executing commands. All 14 cases passed (guard-receipt.txt). timeout 300 python3 scripts/mac_ops_fast_check.py passed with 44 existing tests. No existing test edited or weakened. Device, handset and live-service cases were waived by Shyam, not failed. No live activation occurred. Diff/comment cleanup found no additional changes; no build-rule exceptions introduced.
