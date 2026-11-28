#!/bin/sh
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
cd "$tmp"
git init -q -b main .
git config user.email proof@example.com
git config user.name proof
mkdir coordinator scripts tests
echo base > coordinator/a.py
echo base > tests/test_a.py
git add -A
git commit -qm base
git update-ref refs/remotes/origin/main HEAD

size() { python3 "$root/coordinator/bin/ticket" size --issue 7 2>&1; }
branch() { git checkout -q main; git checkout -q -b "$1"; }
commit() { git add -A; git commit -qm "$1"; }
fail() { echo "FAIL: $1"; exit 1; }

branch small
seq 1 40 > coordinator/b.py
seq 1 400 > scripts/proof_b.sh
commit small
out=$(size) || fail "small change refused: $out"
echo "$out"
echo "$out" | grep -q "runtime lines: 40 (cap 150)" || fail "runtime count"
echo "$out" | grep -q "proof lines: 400" || fail "proof count"
echo "$out" | grep -q "code files: 1 (cap 3)" || fail "file count"
echo "$out" | grep -q "evidence/MO-7/check-proof.md missing" || fail "proof file state"

branch big
seq 1 160 > coordinator/c.py
commit big
out=$(size) && fail "160 runtime lines passed"
echo "$out" | grep -q "over the cap: 160 runtime lines" || fail "cap message: $out"

branch edit
echo more >> tests/test_a.py
commit edit
out=$(size) && fail "edit of an existing test passed"
echo "$out" | grep -q "edited an existing proof or test: tests/test_a.py" || fail "edit message: $out"

branch nobase
git update-ref -d refs/remotes/origin/main
out=$(size) && fail "missing base ref passed"
echo "missing base ref exits non-zero: $out"
echo "ticket size proof: ok"
