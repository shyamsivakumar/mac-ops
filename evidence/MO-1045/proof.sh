#!/bin/sh
set -e
cd "$(git rev-parse --show-toplevel)"
export COORD_JOURNAL_DIR="$(mktemp -d)" COORDQ_DIR="$(mktemp -d)"
cd coordinator/overnight
PYTHONPATH=.:../bin python3 -c '
import selftest
selftest.build_here()
print("PASS build-here: owned PR journals fix_skipped_owned with no herdr-build card; unowned PR still raises it")
'
