#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

remote=0
if [ "${1:-}" = --remote ]; then
    remote=1
    shift
fi
[ $# -eq 3 ] || { echo "usage: $0 [--remote] <branch> <sha> <proof-path> (local mode checks the current tree and ignores <sha>)" >&2; exit 2; }
branch=$1
sha=$2
proof=$3
printf '%s' "$sha" | grep -Eq '^[0-9a-f]{40}$' || { echo "remote_fast_check: sha must be 40 lowercase hex characters" >&2; exit 2; }
printf '%s' "$branch" | grep -Eq '^[A-Za-z0-9._/][A-Za-z0-9._/-]*$' || { echo "remote_fast_check: invalid branch name" >&2; exit 2; }
printf '%s' "$proof" | grep -Eq '^evidence/[A-Za-z0-9._/-]+\.md$' || { echo "remote_fast_check: proof must be evidence/<path>.md" >&2; exit 2; }

if [ "$remote" = 0 ]; then
    waiting=$(heavy status | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["queue"]))')
    [ "$waiting" -ge 3 ] && remote=1
fi
if [ "$remote" = 0 ]; then
    exec heavy python3 scripts/mac_ops_fast_check.py --proof "$proof"
fi

ssh m1 'zsh -l -s' <<EOS
missing=0
for tool in git uvx heavy python3; do
    command -v \$tool >/dev/null || { echo "remote_fast_check: m1 is missing \$tool" >&2; missing=1; }
done
[ -x /opt/homebrew/opt/openjdk@17/bin/java ] || { echo "remote_fast_check: m1 is missing openjdk@17" >&2; missing=1; }
[ -f \$HOME/Code/llmwiki/runtime/tla/tla2tools.jar ] || { echo "remote_fast_check: m1 is missing tla2tools.jar" >&2; missing=1; }
hostname
exit \$missing
EOS

captured=$(mktemp)
trap 'rm -f "$captured"' EXIT
status=0
ssh m1 'zsh -l -s' >"$captured" <<EOS || status=$?
repo=\$HOME/Code/mac-ops
git -C \$repo fetch origin main $branch >&2
dir=\$(mktemp -d /tmp/fastcheck-XXXXXX)
git -C \$repo worktree add --detach \$dir $sha >&2
trap 'git -C \$repo worktree remove --force \$dir && echo "remote_fast_check: removed \$dir on m1" >&2' EXIT
cd \$dir
check=0
heavy python3 scripts/mac_ops_fast_check.py --proof $proof >&2 || check=\$?
cat $proof
exit \$check
EOS

grep -qxF "Checked commit: \`$sha\`" "$captured" && grep -q '^Host: ' "$captured" || {
    echo "remote_fast_check: m1 returned no proof for $sha" >&2
    exit 1
}
mkdir -p "$(dirname "$proof")"
cp "$captured" "$proof"
exit "$status"
