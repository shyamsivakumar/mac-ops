# Host-folder CI caches (MO-120)

Shyam approved (2026-11-02) marking his personal Woodpecker repos
**Trusted (Volumes)** so Linux (Colima) and native macOS agents can mount
host folders that `main` keeps warm. Slash-eureka / org GitHub Actions repos
are out of scope.

Canonical copy of the apply scripts lives under
[`scripts/woodpecker-ci/`](../scripts/woodpecker-ci/). Install onto the M1
with `./scripts/woodpecker-ci/install-to-m1.sh` (MO-117 layout).

## Path convention

```text
/var/lib/woodpecker-cache/<repo>/<kind>/
```

| Segment | Meaning |
| --- | --- |
| `<repo>` | GitHub repo name only (`mac-ops`, `cairn`, …) |
| `<kind>` | `npm` · `node_modules` · `pip` · `spm` · `DerivedData` · `tools` |

- **Colima VM** (Docker agents `ci-linux` / `ci-deploy`): path is inside the
  VM disk. Create with `./setup-cache-dirs.sh --colima`.
- **macOS host** (native agent; later the iMac): same absolute path on the
  host. Create once with `sudo ./setup-cache-dirs.sh --host`.
- Permissions: Colima `root:root` `0750`; macOS `root:admin` `0770`. Only CI
  (and admins) write there.

## Mark Trusted (Volumes) only

```sh
ssh m1 ~/Code/woodpecker-ci/scripts/set-trusted-volumes.sh
# undo all listed:
ssh m1 ~/Code/woodpecker-ci/scripts/set-trusted-volumes.sh --undo
```

Sets `trusted.volumes=true` via the admin API. Leaves `network` and
`security` (privileged) **false**. API-only — does not drain or restart
agents (coordinate with MO-117; never restart during an SRW deploy).

Repos (personal only): `strategy-replay-workbench`, `mac-ops`,
`sams-llm-wiki`, `cairn`, `catalouge`, `recoup`, `CineJar`, `scrapers`,
`scripture-scroll`, `qabot`, `fantasy-football-toolkit`, `strata`.

Per-repo undo (example):

```sh
# PATCH /api/repos/<id>  {"trusted":{"volumes":false}}
```

## How a workflow mounts a cache

Repository must be Trusted (Volumes). Use absolute host paths:

```yaml
steps:
  - name: install
    image: node:22-bookworm
    volumes:
      - /var/lib/woodpecker-cache/cairn/npm:/cache/npm
      - /var/lib/woodpecker-cache/cairn/node_modules:/cache/node_modules
    environment:
      npm_config_cache: /cache/npm
    commands:
      - |
        set -eu
        LOCK_HASH=$$(sha256sum package-lock.json | cut -d" " -f1)
        KEY=/cache/node_modules/$$LOCK_HASH
        MAIN_KEY=/cache/node_modules/main
        if [ "$$CI_PIPELINE_EVENT" = "push" ] \
          && [ "$$CI_COMMIT_BRANCH" = "main" ]; then
          npm ci --cache /cache/npm
          mkdir -p "$$KEY"
          cp -a node_modules/. "$$KEY/"
          ln -sfn "$$LOCK_HASH" "$$MAIN_KEY.Target"
          # publish main pointer after a successful write only
          mv -f "$$MAIN_KEY.Target" "$$MAIN_KEY"
        else
          # PRs / topic branches: read only — never overwrite main's tree
          if [ -d "$$KEY" ]; then
            cp -a "$$KEY/." node_modules/
          elif [ -L "$$MAIN_KEY" ] || [ -f "$$MAIN_KEY" ]; then
            TARGET=$$(cat "$$MAIN_KEY" 2>/dev/null || readlink "$$MAIN_KEY")
            cp -a "/cache/node_modules/$$TARGET/." node_modules/ \
              || npm ci --cache /cache/npm
          else
            npm ci --cache /cache/npm
          fi
        fi
```

`mac-ops` `.woodpecker/fast-check.yaml` mounts
`/var/lib/woodpecker-cache/mac-ops/tools` for pinned CLI / TLA downloads as
the proof path. Those keys are content-addressed (version + sha256): a
missing key may be filled after checksum verify from any event; only
`main` may replace an existing key. Dependency kinds (`npm`,
`node_modules`, `pip`, …) stay strict main-write / PR-read.

## Rule: main writes, PRs only read

Woodpecker has no per-branch cache scope. Branch pipelines in a Trusted
repo can mount the same host paths, so discipline is in the workflow:

1. **Key** by lockfile hash (or pinned tool digest). Prefer the matching
   key; **fall back** to `main`'s published pointer when the PR key is cold.
2. **Pushes to `main`** may populate / rotate the key and update the `main`
   pointer after a successful install.
3. **Pull requests and topic branches** restore only. They must not
   `rm -rf` or overwrite `main`'s pointer or another key owned by main.
4. Caches hold **dependency / tool artifacts only — never secrets**, tokens,
   `.env`, deploy keys, or forge credentials.

## Size cap and cleanup

Default cap: **20 GiB** across `/var/lib/woodpecker-cache` (host + Colima).

```sh
# Manual:
CACHE_ROOT=/var/lib/woodpecker-cache CAP_BYTES=21474836480 \
  ~/Code/woodpecker-ci/scripts/cache-cleanup.sh
```

LaunchAgent `com.shyamsivakumar.woodpecker-cache-cleanup` runs daily at
**04:15** local and prunes oldest `<repo>/<kind>` trees until under the
cap. Bootstrap after `install-to-m1.sh`:

```sh
ssh m1 'DOMAIN=gui/$(id -u)
  launchctl bootout \
    "$DOMAIN/com.shyamsivakumar.woodpecker-cache-cleanup" \
    2>/dev/null || true
  launchctl bootstrap "$DOMAIN" ~/Code/woodpecker-ci/com.shyamsivakumar.woodpecker-cache-cleanup.plist
  launchctl enable "$DOMAIN/com.shyamsivakumar.woodpecker-cache-cleanup"'
```

## Security note

Any branch pipeline in a Trusted (Volumes) repo can mount these host
paths. Treat the tree as world-readable to every workflow author on that
repo. Store **caches only** (package stores, `node_modules` clones, pip
wheels, SPM checkouts, DerivedData, pinned CI tools). Never place secrets
or production credentials under `/var/lib/woodpecker-cache`. Prefer
`trusted.volumes` alone — do not enable `trusted.network` or
`trusted.security` for cache mounts.

## Coordinate with MO-117

Creating directories and PATCHing repo trust do **not** restart agents.
Do not `colima stop`, recreate Docker agents, or reload the native agent
while an SRW `deploy` workflow is running. See
[`docs/m1-ci-lanes.md`](m1-ci-lanes.md).
