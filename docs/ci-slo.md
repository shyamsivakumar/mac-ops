# Cross-repo CI SLO (MO-118)

Shyam's bar lives in
`/Users/shyamsivakumar/Code/coordinator/evidence/ci-standard-2026-11-02.md`
section 4: measure wait / run / total (p50, p95) per repo and workflow, classify
failures as code / infra / flaky, and keep p95 total ≤ 15 minutes with zero
infra failures over a working day.

mac-ops owns the Woodpecker-wide report and guards. **Do not** add
`scripts/ci_slo_report.cjs` (or equivalent) in SRW or other repos — SRW-349
drops its copy; this is the single owner.

## Report

```sh
# From any machine with SSH Host m1:
./scripts/woodpecker-ci/ci_slo_report.sh \
  --md-out /tmp/ci-slo.md --json-out /tmp/ci-slo.json

# On the M1:
./scripts/woodpecker-ci/ci_slo_report.sh --local
```

Daily at **17:00 PT** the M1 LaunchAgent
`com.shyamsivakumar.woodpecker-ci-slo-daily` runs
`ci_slo_daily.sh`, which posts:

- `/Users/shyamsivakumar/Code/coordinator/evidence/ci-slo-<YYYY-MM-DD>.md`
- `/Users/shyamsivakumar/Code/coordinator/evidence/ci-slo-<YYYY-MM-DD>.json`

## Server-wide timeouts (coordinate with MO-117)

| Knob | Value |
| --- | --- |
| `WOODPECKER_DEFAULT_PIPELINE_TIMEOUT` | **15** minutes (new repos) |
| `WOODPECKER_MAX_PIPELINE_TIMEOUT` | 60 minutes |
| Existing repos | `timeout = 15` |
| Override: `strategy-replay-workbench` | `timeout = 30` (deploy budget) |

Apply on the M1 after `install-to-m1.sh` (drains agents first, same as MO-117):

```sh
./scripts/woodpecker-ci/install-to-m1.sh
ssh m1 ~/Code/woodpecker-ci/scripts/set-repo-timeouts.sh
```

`--db-only` updates repo rows without recreating the server.

## `woodpecker-cli lint` on every PR

Shared snippet:
[`scripts/woodpecker-ci/snippets/woodpecker-lint-step.yaml`](../scripts/woodpecker-ci/snippets/woodpecker-lint-step.yaml)

Each repo's PR check should include that step (mac-ops already does in
`.woodpecker/fast-check.yaml`). Per-repo CI-standard tasks (JAR-27, CRN-12,
…) copy it in; slash-eureka repos open a PR only.

Minimal line to add under `steps:` (prefer the full pinned snippet):

```yaml
  - name: woodpecker-lint
    image: alpine:3.22@sha256:2e0b81d60597f449baa56dc25d355367869d2dca4cd57e866f1e2b52af3eb55f
    commands:
      - |
        set -eu
        VER=3.16.0
        ARCH=$(uname -m)
        case "$ARCH" in
          aarch64|arm64)
            WARCH=arm64
            SUM=9c7e6cad9e9d65da8678f8446805076212dd04cad59765d24a0b2b74ac56ed23
            ;;
          x86_64)
            WARCH=amd64
            SUM=a87df7024f2cf4949a94fb27a49808b984350cf97d4aa511049d58f88dd21e7e
            ;;
          *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
        esac
        apk add --no-cache -q curl tar
        curl -fsSL -o /tmp/wp-cli.tgz \
          "https://github.com/woodpecker-ci/woodpecker/releases/download/v${VER}/woodpecker-cli_linux_${WARCH}.tar.gz"
        echo "${SUM}  /tmp/wp-cli.tgz" | sha256sum -c -
        tar -xzf /tmp/wp-cli.tgz -C /usr/local/bin woodpecker-cli
        woodpecker-cli lint .woodpecker/
    when:
      - event: [pull_request, push]
```

## Lanes (MO-117)

Timeout apply and the daily report use the same M1 stack as the two Linux
lanes (`ci-linux` / `ci-deploy`). Never recreate the server during an SRW
deploy; `set-repo-timeouts.sh` calls `drain-agent.sh` first.
