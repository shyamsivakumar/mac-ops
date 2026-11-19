#!/bin/bash
# The verifier runs in the agent sandbox, so it can read what the agent wrote.
# It writes the reward: 1 when the task is done, 0 when it is not.

set -u

mkdir -p /logs/verifier

if [ -f /app/hello.txt ] && [ "$(cat /app/hello.txt)" = "hello harbor" ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

cat /logs/verifier/reward.txt
