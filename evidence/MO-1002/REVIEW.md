# MO-1002 bounded review

Status: source review complete; activation is outside this ticket. Run ticket:shyamsivakumar/mac-ops#341:a1.

Requires verified: approved brief, five owned coordinator sources present, lane.md present and incident decisions 2026-11-14 19:30 and 19:45 read. Initial HEAD was 8c93527bba09fcda8c3cf033c7ca9aa11ee9f5b0; continuation refreshed origin/main and branched from c61f660 (full base recorded in base.txt). Provides remains unfulfilled until a reviewed PR merges.

## Identity and method

The three identity JSON receipts record exact npm versions, tarball URLs, registry integrity, verified SHA-512 and gitHead. Downloaded through Python urllib with its default user agent. Compared GitHub raw entrypoints at each gitHead byte-for-byte with npm contents; all three match (github-receipts.json). This proves entrypoint identity, not complete repository equivalence. Sources are retained solely as review evidence. No package was imported, installed or executed. No credentials or .env were read. Review network requests reached registry.npmjs.org and raw.githubusercontent.com only.

Reproduce: fetch https://registry.npmjs.org/NAME/VERSION with urllib.request.urlopen; fetch dist.tarball; compare base64(hashlib.sha512(bytes).digest()) with dist.integrity; inspect tarfile members as bytes without execution; compare src/index.ts (checklist: dist/index.js) with https://raw.githubusercontent.com/championswimmer/NAME/GITHEAD/PATH. Identity receipts contain NAME, VERSION and GITHEAD. No lifecycle scripts were run.

## Established source contracts

Monitor src/index.ts:62-76 sends customType pi-background-monitor:event, content supplied by LiveInbox, display true, details { batchId, mode }. Wake uses { deliverAs: followUp, triggerTurn: true }; other model delivery uses nextTurn. Its tool description at line 328 explicitly says alerts contain metadata, not output, and watches run only in the live session. Watches must be reconstructed after restart; persisted capture/session locator is not a durable watch subscription. Do not infer guaranteed wake delivery or action completion.

Monitor src/storage.ts uses XDG_STATE_HOME when absolute, otherwise ~/.local/state. manager.ts writes command scripts and capture runtime files and tmux.ts spawns tmux. The package exposes execution capabilities; installing the whole package does not establish a read-only watcher. A restricted integration still needs explicit tool selection and review of all internal command paths.

Checklist README.md:47,83-109 documents ten session tasks, metadata disabled by default, /checklist settings meta to enable and /checklist settings no-meta to disable. dist/index.js seeds metaEnabled false. Settings persist in <agentDir>/pi-checklist.json; tasks persist through session JSONL entries/tool results. Ten tasks cannot represent an unbounded backlog; the lane must remain authoritative.

Subagent manager src/orch/runtime.ts imports createAgentSession and creates child sessions. src/ui/settings-ui.ts describes an optional model status summary which transmits task and recent tool arguments/text to its selected model and consumes extra tokens. Child provider access and persistence require further path-by-path review. Do not treat this package as a passive event producer.

## Coordinator boundary

coordinator.ts:275-285 checks only bash, write, edit and read tool names. Package custom tool names and internal fs/child_process calls are outside that guard. coordinator.sb allows default, including network and reads, while denying writes to specified repository/config trees and allowing Code/coordinator. This is not a network or secret-read sandbox. Writes under the coordinator workspace are allowed; writes under other Code repositories and worktrees conflict. External tmux servers may not share the client sandbox; inheritance must not be assumed without proof. No sandbox changes made.

settings.json currently defaults to pi-claude-cli/claude-opus-5-5; coord-pi also passes that model explicitly. Existing DeepSeek compaction override names do not prove a supported provider default. The repository-supported tick default is COORD_TICK_MODEL=deepseek/deepseek-flash (coordinator/pi/bin/coord-tick:20,41). For a future root default the settings keys are defaultProvider: deepseek and defaultModel: deepseek-flash; coord-pi must also stop overriding it on the CLI. These are source contracts, not a live provider-availability claim. Installer copies owned files; no live installer was run.

## Checks and remaining work

python3 scripts/mac_ops_fast_check.py: PASS (fast-check.txt).
~/.local/bin/heavy python3 -m unittest discover -s tests -t .: PASS, 287 tests (full-check.txt). Full-suite command identified in repository evidence/MO-240/decisions.md:313. No new tests or production edits.

Continuation authorized completion and waived live testing. Ready for coordinator-owned Opus gate; builder does not merge or start another ticket. Full repository equivalence and live provider availability are not claimed. The retained source and contract index make this static review reproducible. No runtime integration guarantee is inferred from static inspection.

## Completed integration decisions

Subagent manager src/orch/runtime.ts:231-280 resolves root/parent model, type preferences and restored model; prefs/settings.ts:85 defaults modelSelection to pick-first-scoped. Use modelSelection: "use-current" to inherit the root model consistently; alternatively type models: ["deepseek/deepseek-flash"] is a supported explicit preference, contingent on registry availability and scope. No guessed package defaultModel key is required. Empty scope is unrestricted, not deny-all (docs/settings.md:180-210). Keep future tool filtering at allowed with explicit allow entries; default all-except-blocked is too broad for this coordinator contract.

runtime.ts:374-392 references agentDir models.json/models-store.json, registers provider configurations and mirrors runtime auth through the SDK. Review did not read those files or invoke auth APIs. Child sessions use the root cwd, provider SDK and a tool allowlist; they can make provider network calls. Housekeeping summaries are optional additional disclosure. OS deny rules still apply to in-process SDK writes, but external bridged services require their own authority boundary. Session histories/registries restore logical state, not a promise that interrupted work resumes safely. Package tools do not establish the coordinator's action policy.

Checklist has checklist_create/read/update tools, session appendEntry persistence, and global preference writes to agentDir/pi-checklist.json. Those writes are allowed in agent-coordinator, but would conflict with the denied ~/.pi/agent tree if PI_CODING_AGENT_DIR were omitted. Monitor uses child_process/tmux and capture files under state storage. Its start/stop/capture capabilities must remain inaccessible to the read-only event producer; use existing lane actions for remediation. Network is permitted by sandbox, not constrained to providers. Neither package guard coverage nor sandbox prevents arbitrary readable-secret access by trusted extension code. No broader permission is needed or recommended.

Static review acceptance: exact versions and SHA-512 receipts match; GitHub entrypoint identities match; source paths establish all requested settings and caveats. No package code execution, live install, parallel scheduler, sandbox weakening, new tests, or edits outside evidence/MO-1002. Existing full suite passed in the initial turn; continuation runs only the required fast check. Documentation cleanup applied to this report; vendored evidence is excluded from deslop/no-comments edits. No production code rule breaks introduced. All runtime/device checks are waived by the continuation, not reported as passes.

Reproduction: timeout 300 python3 evidence/MO-1002/reproduce.py. This downloads and inspects public bytes only; it never imports package code. Executed with a temporary HOME; download-receipt.txt records verified identities. capture.mjs writes capture-state/proof/heartbeat files; these are additional internal fs operations outside tool_call interception.
