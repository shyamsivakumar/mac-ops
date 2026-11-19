# MO-633 oracle and nop results

Harbor 0.26.0, each run through `heavy`, no model agent. Oracle applies the merged diff; nop changes nothing (the parent commit plus the PR's test files).

| Task | Oracle reward | Nop reward | Kept |
| --- | --- | --- | --- |
| mac-ops-619 | 1 | 0 | yes |
| mac-ops-618 | 1 | 0 | yes |
| mac-ops-608 | 1 | 0 | yes |
| mac-ops-597 | 1 | 0 | yes |
| mac-ops-547 | 0 | not run | no |
| mac-ops-542 | 1 | 0 | yes |
| mac-ops-509 | 0 | not run | no |
| mac-ops-486 | 1 | 0 | yes |
| mac-ops-474 | 0 | not run | no |
| mac-ops-471 | 0 | not run | no |
| mac-ops-457 | 0 | not run | no |
| mac-ops-340 | 1 | 0 | yes |
| mac-ops-315 | 1 | 0 | yes |
| mac-ops-312 | 1 | 0 | yes |
| mac-ops-308 | 0 | not run | no |
| mac-ops-273 | 1 | 0 | yes |
| mac-ops-223 | 1 | 0 | yes |
| mac-ops-569 | 1 | 0 | yes |
| mac-ops-510 | 1 | 0 | yes |
| mac-ops-231 | 1 | 0 | yes |
| srw-1309 | 1 | 0 | yes |
| srw-1324 | 1 | 0 | yes |
| srw-727 | 1 | 0 | yes |
| srw-142 | 1 | 0 | yes |

## Dropped candidates (oracle reward 0, environment dependent)

- mac-ops-547, mac-ops-457, mac-ops-308: the tests call `t3mcp`, which exists only on the Mac.
- mac-ops-509: the test expects a RecursionError at the Mac's recursion depth.
- mac-ops-474: the install smoke check runs `/opt/homebrew/bin/python3`.
- mac-ops-471: the test needs an authenticated `gh`.

herdr-projects and sams-llm-wiki were not built. herdr-projects is a Rust build with Linear (SHE-) tickets that have no GitHub text; the sams-llm-wiki PRs in the window are TypeScript skill and hook changes whose tests were not triaged in the time box.
