#!/bin/sh
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
python3 -c "import json,sys;f=json.load(open('runtime/agents/deny-rules.json'))['families'];print(f['push_personal']['mode'],f['push_protected']['mode']);sys.exit((f['push_personal']['mode'],f['push_protected']['mode'])!=('deny','ask'))" && test -x scripts/hooks/pre-push
echo "ticket proof exit $?"
guard() {
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"%s"}' "$2" "$1" | python3 "$ROOT/runtime/agents/deny-merge-guard.py" | python3 -c "import sys,json;d=sys.stdin.read();print(json.loads(d)['hookSpecificOutput']['permissionDecision'] if d.strip() else 'allow')"
}
G=$(mktemp -d)
for kind in personal:https://github.com/shyamsivakumar/mac-ops.git other:git@github.com:other-org/work.git; do
    git init -q "$G/${kind%%:*}"; git -C "$G/${kind%%:*}" remote add origin "${kind#*:}"
done
mkdir "$G/norepo"
echo "guard personal repo, push origin main: $(guard "$G/personal" 'git push origin main')"
echo "guard other remote, push origin main: $(guard "$G/other" 'git push origin main')"
echo "guard unresolvable remote, push origin main: $(guard "$G/norepo" 'git push origin main')"
echo "guard personal repo, push origin work: $(guard "$G/personal" 'git push origin work')"
echo "guard personal repo, force push: $(guard "$G/personal" 'git push --force origin work')"
HOOK="$ROOT/scripts/hooks/pre-push"
T=$(mktemp -d)
git init -q --bare "$T/remote.git"
git init -q -b work "$T/clone"
cd "$T/clone"
git config user.email t@example.com
git config user.name t
git config core.hooksPath "$ROOT/scripts/hooks"
echo a > f; git add f; git commit -qm one
git branch -M main
git checkout -q -b work
try() { echo "--- $1"; shift; "$@"; echo "exit $?"; }
git remote add origin "$T/remote.git"
try "new work branch" git push origin work
echo b >> f; git commit -qam two
try "fast-forward work branch" git push origin work
try "push to main" git push origin work:main
try "push to master" git push origin work:master
git -C "$T/remote.git" update-ref refs/heads/main "$(git rev-parse main)"
try "delete main" git push origin :main
git -C "$T/remote.git" for-each-ref --format="main still at %(objectname)" refs/heads/main
git commit -q --amend -m two-rewritten
try "force push work branch" git push --force origin work
try "force-with-lease work branch" git push --force-with-lease origin work
try "delete work branch" git push origin :work
try "new branch after refusals" git push origin work:work2
echo "--- remote refs"; git -C "$T/remote.git" for-each-ref --format='%(refname)'
