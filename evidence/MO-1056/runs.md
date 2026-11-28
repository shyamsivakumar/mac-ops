# MO-1056 runs

Hook change: llmwiki PR https://github.com/shyamsivakumar/sams-llm-wiki/pull/297 (`plankton-multi-linter.sh`).

Red on main (no `format_skip_paths` support): an edited `scripts/a.sh` with
`format_skip_paths: ["scripts/"]` set is rewritten by shfmt (`cmp` reports a difference).

Green on the branch: the same file stays byte-identical; `lib/b.sh` outside the skip list is still formatted
(`echo   hi` becomes `  echo hi`). A `lib/*.sh` glob flips it the other way.
