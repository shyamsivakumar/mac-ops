# Installation and migration

```mermaid
stateDiagram-v2
    [*] --> Checkout
    Checkout --> Installed: install without legacy state
    Checkout --> Draining: install --migrate
    Draining --> Draining: legacy identity still live
    Draining --> Installed: finalize-migration after last legacy helper exits
    Installed --> Installed: install updated checkout into new content digest
    Installed --> AgentParity: install.sh agents
    AgentParity --> Installed: receipt at ~/.local/state/mac-ops/agents-installation.json
    Installed --> Uninstalled: uninstall archives wrapper and plists
    Uninstalled --> Installed: install
```

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
