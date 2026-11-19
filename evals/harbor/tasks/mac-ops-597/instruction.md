# MO-1103 · Provider block writer with expiry, fresh from main (re-cut of #585)

## Goal and why
Re-cut of PR #585 (MO-1098 provider block writer, 129 lines) after 3 failed rounds (Shyam: re-cut, 2026-11-18). Start fresh from origin/main; read #585 and the reviews below and design so none of those findings can apply.

## Stated behavior change
One function writes a provider block to ~/Code/coordinator/queue/providers-blocked.json atomically (temp file and rename) with an expiry time; reading the file drops entries past their expiry. Nothing calls it yet (wiring is a later ticket).

## Scope and non-goals
In: the writer and expiry on read. Out: callers, parsing limit messages, UI.

## Context
The existing reader of providers-blocked.json (find it; extend that owner module, no new file if it fits). Manual entries without an expiry must stay forever.

## Acceptance and proof
Replay tests: write then read; expired entry dropped; manual entry without expiry kept; two writers at once leave valid JSON with both entries; a corrupt file is not overwritten blindly (one log line, refuse).

## Must not cause
Losing manual blocks; an unblocked provider that is really out of quota; a half-written file.

## Design fit
Extend the reader's module; HARD LIMIT about 120 lines with tests. Self-review with a different model before opening the PR; list findings in the body.

## Data/secrets and stop conditions
No secrets. 15 minutes.

## Earlier review findings to avoid
sivakumar/mac-ops/pull/585) records fixes after three failed review rounds. The convergence rule now requires a smaller PR or Shyam’s decision. [Ticket #575](https://github.com/shyamsivakumar/mac-ops/issues/575) remains open. Local `main` was untouched.

**Bar applied:** The standard merge bar applies because the change handles provider availability. The three-round convergence limit also applies.

**Major — [coordinator/bin/models.py:215](https://github.com/shyamsivakumar/mac-ops/blob/477727df07ae541edf22c6564c07d37f70a1df84/coordinator/bin/models.py#L215).** For a valid selection, `worker exited 1: HTTP 429 Too Many Requests; retry in 30 seconds` returns `False` and records no block. The word `exited` overrides the explicit provider refusal. The subprocess filter should distinguish a process exit code from an HTTP status in the same message.

The earlier failing cases are resolved by inspection:

| Round | Findings and resolution |
|---|---|
| 1 | The authentication filename is ignored. `try in 30 seconds` parses as 30 seconds. The autumn clock change uses the next local calendar day. |
| 2 | The rate-limiter filename is ignored. The parser reads the full `America/Argentina/Buenos_Aires` zone. |
| 3 | Both local subprocess examples are ignored. A delayed shorter refusal preserves an active longer block. |

I reconfirmed the pinned head and the exact PR-body line `Builder check: PASS 477727df07ae541edf22c6564c07d37f70a1df84`. All ten proof rows say `passed`. The checked commit `3eb54641` is an ancestor. Its only diff to the head **modifies** the existing proof file, while the requested check said it should **add** that file. The runtime code is identical across those commits. I did not rerun the suite.

CHECK: FAIL 477727df07ae541edf22c6564c07d37f70a1df84
VERDICT: FAIL

---
rker exited with code 429` matches `code 429`. With a valid selection, `block_provider` records a one-hour provider block. That violates #575’s explicit requirement that a non-provider error block nobody. This concrete failing input blocks round 3 under the convergence rule.

**Major** at `coordinator/bin/models.py:219`. If two refusals arrive out of order, the older one can release the provider early. For example, record a 12:05 failure with a 14:00 reset, then deliver a delayed 12:00 failure with a 12:30 reset. The second write overwrites the newer record, making the provider eligible at 12:30.

**Prior findings.** All five reported cases are resolved in the diff. The two `FileNotFoundError` examples return before writing. `try in 30 seconds` parses as 30 seconds. The autumn clock change uses the next local calendar day. The zone parser consumes all of `America/Argentina/Buenos_Aires`.

**Bar applied.** The standard merge bar applies because this changes provider routing and expiry. The diff touches no stop, exit or trade execution logic.

**Check evidence.** I reconfirmed the PR head and exact body line `Builder check: PASS 9413b6dd3fa203d1ea2ed3ea745f65b343035fea`. All ten receipt rows passed. The checked commit `cff1a84fb7fe73b7abfd45a81471819216e3eecc` is an ancestor. The only intervening change **modified** the existing proof file. The diff totals 257 changed lines against the ticket’s approximate 200-line limit. I did not rerun the suite.

Round 3 ended without PASS. [PR #585](https://github.com/shyamsivakumar/mac-ops/pull/585) remains unmerged and [issue #575](https://github.com/shyamsivakumar/mac-ops/issues/575) remains open for a smaller re-cut or Shyam’s decision. Local `main` was untouched.

CHECK: PASS 9413b6dd3fa203d1ea2ed3ea745f65b343035fea
VERDICT: FAIL

---
**Merge refused.** Round 2 has two major findings with concrete failing inputs. Both follow directly from the pinned diff. I left #585 and #575 open.

- **Major — [models.py:45](https://github.com/shyamsivakumar/mac-ops/blob/b36d6aab97c9d7c53c4565533e4290e101422de4/coordinator/bin/models.py#L45).** `FileNotFoundError: rate limiter config.json` matches the substring `rate limit`. With a valid selection, the writer records a one-hour provider block for a missing local file. This violates the ticket’s explicit requirement that a non-provider error must never block a provider.
- **Major — [models.py:37](https://github.com/shyamsivakumar/mac-ops/blob/b36d6aab97c9d7c53c4565533e4290e101422de4/coordinator/bin/models.py#L37).** For `429: resets at 09:00 (America/Argentina/Buenos_Aires)` received at 02:00 UTC on November 18, the zone pattern cannot consume the third path component. The optional zone drops out, so the block expires at 09:00 UTC, three hours before the stated 12:00 UTC reset.

**Prior findings.** The exact `authentication.json` case is fixed, though the first finding above shows the broader false-block defect persists. The 30-second retry case is fixed. The New York autumn clock-change case is fixed by advancing the local calendar date before converting to epoch seconds.

I applied the standard merge bar because this diff changes provider routing and expiry. I reconfirmed the pinned PR head and the exact body line `Builder check: PASS b36d6aab97c9d7c53c4565533e4290e101422de4`. All ten proof rows say `passed`. The checked commit `c14cf0d6eaef6e33053cac51ce0d8ad12449e289` is an ancestor, and the only subsequent change adds the proof file. I performed no checkout or suite rerun.

CHECK: PASS b36d6aab97c9d7c53c4565533e4290e101422de4  
VERDICT: FAIL

---
provider error must never block a provider. Require evidence that the provider refused the request. [Pinned classifier](https://github.com/shyamsivakumar/mac-ops/blob/ad4c6761e52d136a5f4808f99cd2a05797c9f949/coordinator/bin/models.py#L41)
- **Major · `coordinator/bin/models.py:32`** — `429: Too many requests. Please try in 30 seconds` is recognized as a refusal, but the relative-time parser misses `try in`. The provider stays blocked for an hour instead of 30 seconds. Accept the ticket’s `in N seconds/minutes` form within a confirmed refusal. [Pinned parser](https://github.com/shyamsivakumar/mac-ops/blob/ad4c6761e52d136a5f4808f99cd2a05797c9f949/coordinator/bin/models.py#L32)
- **Major · `coordinator/bin/models.py:179`** — At noon in New York on October 31, 2026, `resets at 09:00 America/New_York` resolves to 08:00 the next morning. Adding 86,400 seconds crosses the fall clock change and releases the provider an hour early. Advance the local calendar date before converting to epoch seconds. [Pinned rollover](https://github.com/shyamsivakumar/mac-ops/blob/ad4c6761e52d136a5f4808f99cd2a05797c9f949/coordinator/bin/models.py#L179)

**Bar applied.** The standard merge bar applies because the diff changes provider routing and expiry. It touches no order, exit, or trade execution path.

There were no prior gate findings on #585. I reconfirmed the PR head and the exact body line `Builder check: PASS ad4c6761e52d136a5f4808f99cd2a05797c9f949`. The diff is scoped, with no workflow file, unrelated test weakening, or exposed secret. I did not rerun the suite.

Proof file `evidence/MO-575/check-proof.md` is absent. The alternate receipt names `8bc727d1`; the exact-head check is established by the accepted PR-body line.

CHECK: FAIL ad4c6761e52d136a5f4808f99cd2a05797c9f949
VERDICT: FAIL

---
**Major** · `coordinator/bin/models.py:197` — A local error such as `FileNotFoundError: authentication.json` matches `authentication` and records a one-hour provider block. This violates the ticket’s explicit requirement to ignore non-provider errors.

**Major** · `coordinator/bin/models.py:32` — `HTTP 429: quota available in 5 minutes` falls back to one hour. The relative-time parser requires `reset`, `retry`, or `try again` immediately before `in`, so it misses the stated reset.

**Major** · `coordinator/bin/models.py:179` — For a failure at noon on October 31, 2026, `resets at 09:00 America/New_York` resolves to 08:00 the next day. Adding 86,400 seconds crosses the fall-back transition and releases the provider an hour early.

**Minor** · `evidence/MO-1098-575/check-proof.md:4` records a run on `8bc727d1`. The exact-head check is attested separately by the confirmed PR-body line below.

`Builder check: PASS ad4c6761e52d136a5f4808f99cd2a05797c9f949`

The PR carries no proof file at `evidence/MO-575/check-proof.md`.

No prior gate findings were posted on #585. The ticket identifies #560 as the superseded PR. Its size concern is resolved by this smaller diff.

Applied the standard merge bar because the diff changes provider blocking and expiry. The ticket has no explicit Provides section, and its required behavior fails the cases above.

Reconfirmed the pinned head. No checkout, suite run, merge, or issue closure.

CHECK: FAIL ad4c6761e52d136a5f4808f99cd2a05797c9f949
VERDICT: FAIL

---
hyamsivakumar/Code/mac-ops/coordinator/bin/models.py:41) matches `authentication` anywhere. A local `FileNotFoundError: authentication.json` therefore records a one-hour provider block. Match a provider refusal before writing.
- **Major** — [models.py:32](/Users/shyamsivakumar/Code/mac

The repository is at `/app`. Make the change there. Do not edit test files.
