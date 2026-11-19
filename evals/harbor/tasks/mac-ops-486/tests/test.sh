#!/bin/bash
# Copies the PR's own test files over the working tree, runs them, and writes
# the reward: 1 when the tests pass, 0 when they fail.

set -u

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

cd /app || exit 1
cp -R "$(dirname "$0")/files/." /app/ || exit 1

if python3 -m pytest -q -x tests/test_tick_external_call_bounds.py; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt
