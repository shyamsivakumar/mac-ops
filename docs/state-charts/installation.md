# Installation and migration

```mermaid
stateDiagram-v2
    [*] --> Checkout
    Checkout --> Installed: install without legacy state
    Checkout --> Draining: install --migrate
    Draining --> Draining: legacy identity still live
    Draining --> Installed: finalize-migration after last legacy helper exits
    Installed --> Installed: install updated checkout into new content digest
    Installed --> Compared: install_if_behind reads source_commit and origin/main
    Compared --> Installed: source_commit equals origin/main
    Compared --> Deferred: heavy queue above 3 or a host veto
    Deferred --> Compared: a later firing retries
    Compared --> Observing: source_commit is behind and the gate is clear
    Observing --> Observing: agent process exits during census
    Observing --> Installed: required controller ticks arrive within the bound
    Observing --> RolledBack: controller error or slots hit 0 without a veto
    Observing --> RolledBack: bound ends before the required ticks
    Observing --> Unverified: firing killed after the receipt names the new commit
    Unverified --> Installed: next firing reads source_commit equal to origin/main (follow-up)
    RolledBack --> Installed: previous release reactivated
    Installed --> AgentParity: install.sh agents
    AgentParity --> Installed: receipt at ~/.local/state/mac-ops/agents-installation.json
    Installed --> Uninstalled: uninstall archives wrapper and plists
    Uninstalled --> Installed: install
```

`scripts/install_if_behind.py` is the install automation's decision. It treats
the receipt `source_commit` as behind only when that full commit is an ancestor
of `origin/main`. A matching checkout HEAD does not count. A heavy queue above
3 or a host veto defers. After install it watches the controller until the
required ticks arrive or the bound ends. The bound is three minutes from the
start of observation (twelve ticks at one per fifteen seconds). An agent whose
foreground process exits during the census is normal churn and stays in
observation. A controller error, a heavy error, any other census error, or
board slots at 0 without a veto reactivates the previous release. The same
rollback happens when the bound ends without enough ticks or the controller
status is stale.

Observation state lives only in the firing's memory. When a firing is killed
after `install.sh` writes the new receipt and before observation ends, the
`flock` is released and nothing records that the release was never checked.
The next firing sees `source_commit` equal to `origin/main` and returns
`up_to_date`, so the unverified release stays active. The
[install model](../../formal/install-if-behind/README.md) finds this path.

| State | Entered by | Guard to leave | Side effect |
| --- | --- | --- | --- |
| Compared | firing takes the lock | not main, dirty or fetch failed: error; receipt equals origin/main: up_to_date; behind: gate check | none |
| Deferred | gate blocked or lock held | later firing | closing note |
| Observing | receipt names target commit | ticks, controller error, bound end | reads `controller.jsonl` |
| RolledBack | observation failed | previous receipt exists | previous release reactivated |
| Unverified | firing killed in Observing | none recorded | none (follow-up) |

Installation copies an explicit source allowlist into a private runtime
directory and writes each file atomically. It does not replace files used
by existing runtime versions. Migration blocks new admission before
changing old entry points. Old private bootstrap and watchdog calls keep
the original implementation until its supervisors finish.

Finalization requires no surviving legacy supervisor, workload or helper
identity. It retains old job state as history before moving the admission
marker aside. The caller must verify reference inventory and board worker
instructions separately before archiving the old folder. Uninstall
preserves runtime files and state.
