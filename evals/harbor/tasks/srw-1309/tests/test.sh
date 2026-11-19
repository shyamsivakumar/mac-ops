#!/bin/bash
# Copies the PR's own test files over the working tree, runs them, and writes
# the reward: 1 when the tests pass, 0 when they fail.

set -u

mkdir -p /logs/verifier
cd /app || exit 1
cp -R "$(dirname "$0")/files/." /app/

if node test_srw1309_sell_recovery_scope.js; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt
