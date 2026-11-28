# Coordinator hill-climb labels (MO-1199 a)

Cold-start label set built from Shyam's real past decisions. Every label is a
decision the coordinator actually put to him, the answer it recommended, and the
answer he actually gave. Nothing here is invented: a decision is kept only when
the coordinator's recommendation is recorded somewhere (a decisions-board item's
`recommended` option, a `(Recommended: ...)` line in the ask, or the generator
code that raises the card).

Total labels: **133**. Labels with a non-empty `options` list (the ones the
scorer counts): **131**. Free-text labels stay in
`labels.jsonl` but are not scored.

## Files

| File | What it is |
|---|---|
| `labels.jsonl` | One JSON object per label. |
| `split.json` | Seeded FINAL / DEV / HELDOUT id lists (nested, plus flat `final` / `dev` / `heldout` keys that `score.py` reads). |
| `build_labels.py` | Rebuilds both files from the sources. Deterministic. |
| `daily3.py` | Daily 3: `pick` three real decisions, `record` Shyam's answer. |
| `ledger.py` | Preference ledger: one accept, reject, acted or ignored row per answered decision card, joined from `labels.jsonl` and the `decision_*` journal events; writes `preferences.jsonl`. |
| `climb.py` | Keep or revert one change: scores an arm against the incumbent on the locked split, prints KEEP or REVERT, logs to `climb_log.jsonl`. |
| `burst.py` | Mines unanswered thin-kind decisions into `burst_queue.jsonl`. |
| `burst_queue.jsonl` | Mined decisions with no recorded answer, waiting for Shyam. |
| `daily3_guesses.jsonl` | The coordinator's guess, written before each question is shown. |
| `hard_set.jsonl` | Escaped bugs (reached production or a merged PR). Never scored. |
| `arms/plain_agent.py` | No-rules baseline arm: one model call, one option. |
| `README.md` | This file. |

Label keys: `id`, `kind`, `item_text` (the question, max 300 chars), `recommended`
(the coordinator's answer), `answer` (Shyam's answer; the exact option string when
he picked one), `agree` (`true` / `false` / `partial`), `ts`, `source` (file:line of
the answer and of the ask), `options` (the choices the ask offered, verbatim; `[]`
for a free-text ask).

## Sources

1. Coordinator pi session logs,
   `~/.pi/agent-coordinator/sessions/--Users-shyamsivakumar-Code-coordinator--/*.jsonl`.
   Two answer forms:
   - **Board answers**: a user message starting `Decisions:` with lines
     `- <id> (<title>): <answer>`.
   - **Typed answers**: a short user reply directly after an assistant message that
     ends with exactly one question carrying `(Recommended: <answer>)`. Only
     unambiguous pairs are kept; a reply that asks something else, changes the
     subject, or is a screenshot is skipped.
2. Decisions-board items: the `decisions.json` writes in the same logs, the
   `decisions.json*` snapshots under `~/Code/coordinator/` and `backups/`, and the
   `(Recommended: ...)` text in the tick alert that raised the card.
3. Generator code, for cards the lane driver raises itself:
   `~/.local/bin/coordq:2053` (`recut-*`) and
   `~/Code/mac-ops/coordinator/overnight/lane_driver.py:840` (`lane-gate-rounds-*`).
   These record the recommended option in code, so the recommendation is read, not
   guessed.

`~/Code/coordinator/notes.md` and `loop/decisions.md` were read to corroborate
answers. They are dated prose, not per-decision records, so no label cites them as
its primary source.

Only decision text, recommendations and answers are copied. No tokens, keys,
emails or account numbers are in the file.

## Counts per kind

| Kind | Labels | With options | Agree true |
|---|---:|---:|---:|
| access | 9 | 8 | 7 |
| merge | 3 | 3 | 3 |
| model_choice | 19 | 19 | 14 |
| money | 4 | 4 | 3 |
| other | 40 | 40 | 31 |
| recut | 19 | 19 | 19 |
| release | 16 | 16 | 16 |
| size_exception | 9 | 9 | 9 |
| ticketing | 14 | 13 | 13 |
| **total** | **133** | **131** | **115** |

## Splits

Rule (in `split.json` and `build_labels.py`): `h = sha256(id)`; `FINAL` when
`h % 100 < 15`; otherwise `DEV` when `(h // 100) % 100 < 80`, else `HELDOUT`.
The rule depends only on the label id, so a label never moves when more labels are
added.

| Split | Labels | With options | Agree true | Agreement rate |
|---|---:|---:|---:|---:|
| DEV | 91 | 90 | 80 | 87.9% |
| HELDOUT | 18 | 17 | 16 | 88.9% |
| FINAL | 24 | 24 | 19 | 79.2% |

FINAL is the untouched set. Do not score it for keep-or-revert decisions; it is
for an occasional check only (at most once a week, per #843).

## Agreement on DEV (recommended vs Shyam's answer)

Overall: **80/91 = 87.9%** (labels with options: 90/91).

| Kind | DEV labels | With options | Agree true | Rate |
|---|---:|---:|---:|---:|
| access | 8 | 7 | 7 | 87.5% |
| merge | 2 | 2 | 2 | 100.0% |
| model_choice | 15 | 15 | 11 | 73.3% |
| money | 2 | 2 | 2 | 100.0% |
| other | 28 | 28 | 22 | 78.6% |
| recut | 12 | 12 | 12 | 100.0% |
| release | 10 | 10 | 10 | 100.0% |
| size_exception | 8 | 8 | 8 | 100.0% |
| ticketing | 6 | 6 | 6 | 100.0% |

`agree` is kept for reporting only; the scorer does not use it. The scorer compares
`recommended` with `answer` over `options`.

## Repeats and dropped decisions

32 decision ids were answered more than once. The label keeps the
latest answer. The repeats are mostly the same watchdog card re-answered on later
ticks (`factory-watchdog`, `factory-overnight-stall`, `herdr-build-*`). One repeat
matters: `lane-gate-rounds-...-1575` was answered `keep fixing` in chat and then
`Re-cut it into smaller pull requests` on the board; the board answer is the one
kept, and the coordinator's own note says the typed answer won.

31 board decisions were **not** turned into labels:

- Action cards (`factory-watchdog`, `factory-zero-merge`, `factory-overnight-stall`,
  `overnight-selftest`, `lane-close-failed-*`, `herdr-build-*`, `lane-gate-split-*`)
  carry no options and no recommendation, so there is nothing to score.
- Cards whose recommendation was never recorded anywhere readable
  (`ffk-fantrax-window`, `ffk-chrome-bridge`, `ffk-m1-link`, `ctl33-device-setup`,
  `ctl-27-m3-partial-receipt`, `heavy-queue-stuck-2026-11-14`,
  `opus-spend-limit-2026-11-14`, `gate-reviewer-spend-limit-2026-11-14`,
  `srw878-gate-fail-2026-11-14`, `concerning-manual-merges-2026-11-14`,
  `srw-1240-recovery-scope`, `concerning-88-gate-merge`, `m1-amp-login`,
  `concerning-db-copy`, `m1-logins`, `concerning-102-runtime-role`,
  `catalogue-app-group`, `ffbt-vercel-access`).

The full list with reasons is printed by `build_labels.py` into
`$TMPDIR/hc/build_notes.json` on each run.

## Shortfall

131 real labels exist, above the ~100 target, so nothing is padded and no
`needed.md` is written. Thin kinds for future Daily 3 asks: **merge** (3), **money**
(4), **access** (9), **size_exception** (9). `other` is the largest bucket (40) and
should shrink as new asks are classified more precisely.

## Adding Daily 3 labels later without moving existing ones

1. Append new labels to `labels.jsonl` with a stable `id`. Use the decision id for
   board items and `typed-<slug of the question>` for typed asks. Never reuse an id
   for a different decision.
2. Run `python3 build_labels.py` only if you are rebuilding from the logs. It
   rewrites `split.json` from the same hash rule, so existing ids keep their split and recorded rows are preserved.
3. If you add labels by hand, compute the split with the same rule:
   `h = int(sha256(id).hexdigest(), 16)`; `FINAL` if `h % 100 < 15`, else `DEV` if
   `(h // 100) % 100 < 80`, else `HELDOUT`. Add the id to the matching list in
   `split.json`.
4. Never move an id between splits, and never re-cut FINAL. If a label is wrong,
   delete it; do not re-label it into another split.
5. Keep `options` verbatim from the ask. If Shyam picked one, `answer` is exactly
   that option string. A free-text ask gets `options: []` and is not scored.

## Daily 3

Three real decisions a day go to Shyam, and the coordinator's guess is logged
before the question is shown. That ordering is the whole point: the guess cannot
be edited after the answer is known.

```sh
cd ~/Code/coordinator/evals/hillclimb
python3 daily3.py pick      # logs the guess, then prints 3 questions with it hidden
python3 daily3.py record --id <label_id> --choice '<option>' --reason '<one line>'
```

`pick` reads the live inbox (`~/Code/coordinator/decisions.json`) first and, when
that is empty, the mined backlog (`burst_queue.jsonl`). For each item it appends
`{ts, label_id, kind, item_text, options, guess, guess_source}` to
`daily3_guesses.jsonl` and flushes to disk **before** printing anything. The
printed card never shows the guess.

`record` appends the label to `labels.jsonl` with `id, kind, item_text, options,
answer, recommended, recommended_option, agree, ts, source, reason`, routes the id
into `split.json` with the same `sha256(id)` rule, removes the item from
`burst_queue.jsonl`, and re-runs `score.py lock`. An escaped bug (a bug that
reached production or a merged PR) is written to `hard_set.jsonl` with
`--escaped-bug` and never enters DEV, HELDOUT or FINAL.

`burst.py` rebuilds `burst_queue.jsonl` from the same sources `build_labels.py`
uses, keeping only decisions that carry a recorded recommendation and have no
recorded answer, favouring the thin kinds. It prints the first ten with the guess
hidden. An item with no recorded answer stays in the queue until Shyam answers it.

## Gate disagreements

`burst.py --log-disagreements` reads every `events-*.jsonl` in the coordinator
journal (`COORD_JOURNAL_DIR`, else `~/.local/state/coordinator/journal`, backfill
file included) and appends to `gate_disagreements.jsonl` one row per PR whose
third distinct reviewed head has a different final verdict (PASS or FAIL) from
its first. A head's final verdict is its latest `gate_verdict` row. A row holds
the repo, PR, both heads, both verdicts, the round-1 class and both times. A
row is written once per repo, PR and third head, so a second run adds nothing.
A line that does not parse, in the journal or in the log, is skipped. A normal
`burst.py` run does the same append before it rebuilds the queue. Nothing else
changes: no label, split, scorer lock or queue row, and no model call.

A FAIL then PASS pair usually means the code was fixed between the heads, so a
row is a question for Shyam and not a label.

## Data dir

`build_labels.py`, `daily3.py`, `burst.py` and `climb.py` read and write their data in the dir given by `--data DIR`, default the script's own dir when it holds `labels.jsonl`, else `~/Code/coordinator/evals/hillclimb`. Run them from the repo copy with `--data` pointing at a scratch copy to try a change on real data without touching the installed files.

## Rebuild

```sh
cd ~/Code/coordinator/evals/hillclimb && python3 build_labels.py
```

A rebuild keeps every row already in `labels.jsonl` that the logs do not
reproduce, and keeps every row recorded by `daily3.py` (source starting
`daily3 record`) whole even when the logs produce the same id. It raises
`ValueError` with `path:line` on an unparsable line, a row without an id or a
duplicate id, before writing anything. For other rebuilt ids it keeps `reason` and
`recommended_option` on rebuilt ids, fills `recommended_option` on new rows, and
writes `split.json` with the flat `final` / `dev` / `heldout` keys that `score.py`
reads. Both files are written to a temp file and renamed. Re-run `score.py lock`
after a rebuild, because the file hashes change.
