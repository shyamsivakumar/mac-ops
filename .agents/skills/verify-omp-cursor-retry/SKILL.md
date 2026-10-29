---
name: verify-omp-cursor-retry
description: Verify the local omp Cursor retry patch when its provider gate, session veto or execution allowlist changes.
---

# Verify omp Cursor retries

## Property and coverage

An unsafe Cursor turn cannot pass the provider checkpoint retry gate, even
when a fresh checkpoint exists. Replaying a write or shell call can duplicate
a side effect.

The bounded check below reads the actual `replaySafe` expression from the
patched TypeScript AST, evaluates all eight combinations of unsafe,
checkpoint freshness and progress, and rejects a mutation with the unsafe
guard removed. It uses the installed TypeScript parser and the task-local Bun
1.4.4 runtime. It checks a predicate, not network scheduling or the entire
session state machine.

Covered source is `pi-ai/src/providers/cursor.ts` inside
`scripts/omp_cursor_retry.patch`, prepared by `scripts/omp_cursor_retry.py`.
The source revision is omp 18.13.3, pinned by the preparer's preimage and
postimage SHA-256 values. Last checked on mac-ops base `9bd86bc` plus this
patch. Update the hashes and this record together when changing the patch.

## Run

First prepare a copy. Nothing is installed and the destination must be under
this task's TMPDIR.

```sh
scripts/omp_cursor_retry.py apply --root "$TMPDIR/cursor-proof"
export MO35_COPY="$TMPDIR/cursor-proof"
cat > "$TMPDIR/cursor-gate-proof.js" <<'JS'
import { createRequire } from 'node:module';
const require = createRequire(process.env.MO35_COPY + '/node_modules/typescript/package.json');
const ts = require('./lib/typescript.js');
const path = process.env.MO35_COPY + '/node_modules/@oh-my-pi/pi-ai/src/providers/cursor.ts';
const text = await Bun.file(path).text();
const ast = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const predicates = [];
function walk(node) {
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === 'replaySafe' && node.initializer) {
    predicates.push(node.initializer.getText(ast));
  }
  ts.forEachChild(node, walk);
}
walk(ast);
if (predicates.length !== 1) throw new Error('Replay gate declaration is ambiguous or missing');
function verify(expression) {
  const gate = new Function('safety', 'hasFreshCheckpoint', 'sawProgressOrSideEffect', `return (${expression});`);
  let states = 0;
  for (const unsafe of [false,true]) for (const fresh of [false,true]) for (const progress of [false,true]) {
    const actual = gate({unsafe},fresh,progress);
    const expected = !unsafe && (fresh || !progress);
    if (actual !== expected) throw new Error(JSON.stringify({unsafe,fresh,progress,actual,expected}));
    states++;
  }
  return states;
}
console.log('actual replay gate:', predicates[0]);
console.log('bounded states passed:', verify(predicates[0]));
let caught = false;
try { verify('hasFreshCheckpoint || !sawProgressOrSideEffect'); }
catch (error) { caught = true; console.log('removed-unsafe-guard mutant rejected:', error.message); }
if (!caught) throw new Error('Proof did not catch unsafe mutant');
JS
BUN_BE_BUN=1 "$MO35_COPY/runtime" "$TMPDIR/cursor-gate-proof.js"
```

Expected output includes `bounded states passed: 8` and a rejected mutant
with `unsafe:true`. A failure in the real expression is a finding. Do not
weaken the expected predicate to make it pass.

## Runtime obligations

The predicate check does not show that execution sets the flag or that the
session honors it. Also run the same stock/patched network injection harness
before tokens, after text and after a completed local read, for ENOTFOUND and
ECONNRESET. Safe cases must finish with the expected response. Inject after a
write or shell call and after a later read in the same turn. Unsafe cases
must make zero new provider requests after the fault, and the execution log
must contain no duplicate write or shell call.

Finally run ten live `cursor/grok-4.7` turns without injection and report
empty replies, nonzero exits and exact expected replies. Keep the harness,
full logs and command receipts in the task report folder, not in the repo.
The MO-35 proof is in `~/.herdr-projects/reports/mac-ops/35/`.

Also run the report folder's `watchdog-policy.ts` and
`watchdog-session-probe.ts`. Each sends a write, shell or MCP execution frame
from a local HTTP/2 peer and then stalls until the outer watchdog fires. The
second drives a real `AgentSession.prompt()`. Patched runs must show one
request, one handler run, `cursorReplayUnsafe:true`, the blocked prefix and
no `auto_retry_start`. In the session probe stock shows two requests and two
handler runs; in the policy probe stock shows one of each with
`retryable:true`.

Run the report's `blast-radius-classifier-probe.ts` against stock and the
copy. The only allowed differences are bare `ECONNRESET` becoming retryable
and Cursor-API messages exactly equal to `ECONNRESET` becoming transient.
Validation, unauthorized, terminal 4xx and AbortError completion retries must
keep stock's single attempt.

## Limits

The proof covers the eight gate states and the exercised live scenarios.
It does not prove every event ordering, other providers, remote/internal URL
reads, installation or update behavior, or production board routing. Use
`maintain-formal-verification-skill` when the covered lifecycle changes.
