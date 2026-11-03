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
- Permissions: Colima `root:root` dirs `0750`; macOS `root:admin` dirs
  `0770`. Setup only chmods directories so cached executables keep `+x`.
  Only CI (and admins) write there.

## Mark Trusted (Volumes) only

```sh
ssh m1 ~/Code/woodpecker-ci/scripts/set-trusted-volumes.sh
# undo all listed:
ssh m1 ~/Code/woodpecker-ci/scripts/set-trusted-volumes.sh --undo
```

Sets `trusted.volumes=true` via the admin API for an explicit
`owner/name` allowlist. Leaves `network` and `security` (privileged)
**false**. Rejects missing or ambiguous `full_name` matches. API-only —
does not drain or restart agents (coordinate with MO-117; never restart
during an SRW deploy).

Repos (personal only): `shyamsivakumar/strategy-replay-workbench`,
`…/mac-ops`, `…/sams-llm-wiki`, `…/cairn`, `…/catalouge`, `…/recoup`,
`…/CineJar`, `…/scrapers`, `…/scripture-scroll`, `…/qabot`,
`…/fantasy-football-toolkit`, `…/strata`.

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
        if [ "$$CI_PIPELINE_EVENT" = "push" ] \
          && [ "$$CI_COMMIT_BRANCH" = "main" ]; then
          npm ci --cache /cache/npm
          stage=$$(mktemp -d "$$KEY.staging.XXXXXX")
          cp -a node_modules/. "$$stage/"
          rm -rf "$$KEY"
          mv "$$stage" "$$KEY"
          printf '%s\n' "$$LOCK_HASH" > /cache/node_modules/main
        else
          # PRs: restore only a matching lockfile key. Never copy main's
          # node_modules when the lockfile differs — that installs the
          # wrong tree. Fall back to npm ci using the warm package cache.
          if [ -d "$$KEY" ]; then
            cp -a "$$KEY/." node_modules/
          else
            npm ci --cache /cache/npm
          fi
        fi
```

Warm **package-download** caches (`npm`, `pip`, …) are the right fallback
when the lockfile key is cold. A `node_modules` (or equivalent installed
tree) key is only safe to restore when it matches this revision's
lockfile hash.

`mac-ops` `.woodpecker/fast-check.yaml` mounts
`/var/lib/woodpecker-cache/mac-ops/tools` for pinned CLI / TLA downloads as
the proof path. Keys include the artifact digest; every restore re-checks
that digest and discards stale entries. A missing key may be filled after
checksum verify from any event (unique staging dir + lost-race = accept
valid key); only `main` may replace an existing key. Dependency kinds
(`npm`, `node_modules`, `pip`, …) stay strict main-write / PR-read.

## Rule: main writes, PRs only read

Woodpecker has no per-branch cache scope. Branch pipelines in a Trusted
repo can mount the same host paths, so discipline is in the workflow:

1. **Key** installed trees by lockfile hash (or pinned tool digest). Prefer
   the matching key. When it is cold, fall back to a **package-download**
   cache and reinstall (`npm ci`, `pip download`, …) — do not restore
   another revision's installed tree.
2. **Pushes to `main`** may populate / rotate the key after a successful
   install.
3. **Pull requests and topic branches** restore only. They must not
   `rm -rf` or overwrite `main`'s keys.
4. Caches hold **dependency / tool artifacts only — never secrets**, tokens,
   `.env`, deploy keys, or forge credentials.

## Size cap and cleanup

Default cap: **20 GiB per tree** — host and Colima each. Combined usage
can approach 40 GiB. Lower `CAP_BYTES` on either side if disk is tight.

```sh
# Manual:
CACHE_ROOT=/var/lib/woodpecker-cache CAP_BYTES=21474836480 \
  ~/Code/woodpecker-ci/scripts/cache-cleanup.sh
```

LaunchAgent `com.shyamsivakumar.woodpecker-cache-cleanup` runs daily at
**04:15** local and prunes **oldest** (by mtime) `<repo>/<kind>` trees
until under the per-tree cap. It **skips entirely** while any Woodpecker
workflow is `running`, so it does not delete a mounted cache mid-job.
Bootstrap after `install-to-m1.sh`:

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
