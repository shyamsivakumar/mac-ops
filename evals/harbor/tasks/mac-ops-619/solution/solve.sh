#!/bin/bash
# The oracle solution: the merged diff without its test files.

set -euo pipefail

cd /app
git apply --whitespace=nowarn "$(dirname "$0")/fix.patch"
