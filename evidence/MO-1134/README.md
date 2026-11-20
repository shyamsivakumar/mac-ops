# MO-1134: a provider block ends at its `until` time

Ticket: shyamsivakumar/mac-ops#709. The check proof is `check-proof.md` in this
directory.

## What changed

- `coordinator/bin/models.py`: `expiry` reads an ISO 8601 `until` when
  `expires_at` is absent, so an entry written before the `expires_at` rule
  ends at its `until` instead of blocking forever. `expires_at` still wins
  when both are present, and an entry with neither is still a manual block.
- `coordinator/bin/models.py`: `known_identities` names every blocked-store
  identity the four lists can produce, and `blocked_identities` drops an entry
  whose key is not one of them, so a block on a model that left `models.json`
  no longer blocks anything.
- `coordinator/bin/models.py`: `block_provider` already wrote `expires_at`; it
  now also prunes an expired `until`-only entry on write, because `expiry`
  reads `until`. A longer `until`-only block is still never shortened.
- `tests/test_models_block_provider.py`: the expiry test now uses identities
  the lists carry, because an unknown-model entry is pruned. New tests cover
  the `until` rule, the `Z` suffix, a bad `until`, unknown-model pruning, the
  numeric `expires_at` a write produces, and the two writer cases above.
- `docs/model-list.md`: the blocked-providers paragraph states the `until`
  rule and the unknown-model pruning.

## Replay against the live file

`python3 evidence/MO-1134/replay.py` copies the live
`~/Code/coordinator/queue/providers-blocked.json` into a temp `COORDQ_DIR` and
reads and writes only the copy. Output on this head:

```
== the live file, read through the new reader ==
now: 2026-11-20T04:45:03Z
  anthropic-api:claude-opus-5-5: expiry=inf known=True
  glm:glm-5.3: expiry=inf known=False
  openai-api:gpt-6.2-astra: expiry=1795035192.195219 known=True
  minimax:minimax/MiniMax-M3.1-Flash: expiry=inf known=False
  minimax:MiniMax-M3.1-Flash: expiry=inf known=False
blocked now: ['anthropic-api:claude-opus-5-5']

== 1. block_provider writes a numeric expires_at ==
{"expires_at": 1795153503.4931352}

== 2. an until-only entry: a past until is not blocked, a future one is ==
past until   2026-11-20T04:44:03+00:00 -> []
future until 2026-11-20T05:45:03+00:00 -> ['openai-api:gpt-6.2-astra']

== 3. a manual block is kept, an unknown-model entry is pruned ==
-> ['anthropic-api:claude-opus-5-5']

== the live file is untouched ==
sha256 before: e660152e8f9213551d8810124478de64b554890b91ddbf1e9123bb89de6a08fb
sha256 after:  e660152e8f9213551d8810124478de64b554890b91ddbf1e9123bb89de6a08fb
```

The live `openai-api:gpt-6.2-astra` entry carries `until`
`2026-11-18T20:53:12.195219+00:00`, which is in the past at the replay time, so
the new reader no longer blocks it. Before the change `expiry` returned
infinity for that entry and astra-api was skipped on every gate.

## Before and after on the live file

`models.py first review standard` reads the live block file. The old module is
`git show origin/main:coordinator/bin/models.py` loaded from a temp file, so
neither run writes the live file.

```
old blocked: ['anthropic-api:claude-opus-5-5', 'glm:glm-5.3', 'minimax:MiniMax-M3.1-Flash', 'minimax:minimax/MiniMax-M3.1-Flash', 'openai-api:gpt-6.2-astra']
old first review: astra-sub
new blocked: ['anthropic-api:claude-opus-5-5']
new first review: astra-api
```

The first review entry is astra-api again, which is the point of the ticket.

The two `minimax` keys and `glm:glm-5.3` name models no list carries, so the
reader prunes them. `anthropic-api:claude-opus-5-5` is a manual block on a
listed model and stays blocked.

## Acceptance

1. A written block carries a numeric `expires_at`: section 1 above, and
   `test_written_entry_carries_a_numeric_expires_at`.
2. A past `until` is not blocked and a future `until` is: section 2 above, and
   `test_until_only_entry_ends_at_its_until`.
3. A manual block stays blocked and an unknown-model entry is pruned: section 3
   above, and `test_unknown_model_entry_is_pruned_and_a_manual_block_is_kept`.
4. `python3 scripts/mac_ops_fast_check.py --proof evidence/MO-1134/check-proof.md`
   passes on the final head: `check-proof.md`.
