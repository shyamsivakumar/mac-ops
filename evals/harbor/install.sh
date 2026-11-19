#!/bin/sh
# Install the pinned Harbor release this evaluation uses.
#
# Harbor is a Python program, so `uv tool install` puts one pinned release on
# the PATH at ~/.local/bin/harbor without touching the system Python.
set -eu

HARBOR_VERSION=0.26.0

if ! command -v uv >/dev/null 2>&1; then
  echo "install.sh: uv is not on the PATH; install uv first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv tool install "harbor==${HARBOR_VERSION}"

harbor --version
