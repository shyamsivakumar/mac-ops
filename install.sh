#!/bin/sh
set -eu
if ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
  echo 'mac-ops requires Apple Command Line Tools and their Python 3. Install them with xcode-select --install, then retry.' >&2
  exit 1
fi
checkout=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
exec /usr/bin/python3 -I "$checkout/install.py" "$@"
