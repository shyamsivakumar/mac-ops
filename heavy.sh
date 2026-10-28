#!/bin/sh
set -eu

script_path=$0
while [ -L "$script_path" ]; do
  script_dir=$(CDPATH= cd -P "$(/usr/bin/dirname "$script_path")" >/dev/null 2>&1 && pwd)
  link=$(/usr/bin/readlink "$script_path")
  case "$link" in
    /*) script_path=$link ;;
    *) script_path=$script_dir/$link ;;
  esac
done
script_dir=$(CDPATH= cd -P "$(/usr/bin/dirname "$script_path")" >/dev/null 2>&1 && pwd)
exec /usr/bin/python3 -I "$script_dir/heavy.py" "$@"
