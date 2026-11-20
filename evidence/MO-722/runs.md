# MO-722 runs

## Selftest on origin/main coordq (0dfc6efd) with this branch's credit-block case
```
$ cd <copy of coordinator/ with bin/coordq from origin/main> && heavy python3 overnight/selftest.py
PASS key-mint
FAIL credit-block: expected ['openai-api:gpt-6.2-astra'], got []
```

## Selftest on this head
```
$ heavy python3 coordinator/overnight/selftest.py
PASS router-blocked
PASS key-mint
PASS credit-block
```
All 26 cases print PASS.

## In-process block with a temp COORDQ_DIR, no GitHub or thread calls
```
$ python3 show.py   # calls coordq.block_quota_provider twice
after generic 429: []
providers-blocked.json: {"blocked": {"openai-api:gpt-6.2-astra": {"expires_at": 1795159270.000212}}}
dispatch.log: 2026-11-19 22:21:10 blocked provider openai-api:gpt-6.2-astra for 1h: no credits remaining
journal: {"v":1,"ts":1795155670.000654,"event":"provider_blocked","actor":"coordq","repo":"shyamsivakumar/mac-ops","ticket":null,"pr":20,"head":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","thread":null,"item":null,"attempt":null,"kind":"gate","data":{"provider":"openai-api:gpt-6.2-astra","reason":"no credits remaining","seconds":3600}}
```

## Lock order: drain no longer waits for the provider lock under the queue lock
Gate finding on 862eb518: `drain()` called `block_provider` (provider lock) while the caller held the queue lock, the reverse of gatekeep's provider-then-queue order. `drain()` now queues the block and `cmd_enqueue` and `cmd_dispatch` write it after the queue lock is released. The `credit-block` case runs `cmd_dispatch` while another thread holds the provider lock and then asks for the queue lock, with 10 s joins.
```
$ COORDQ_DIR=$(mktemp -d) heavy python3 overnight/selftest.py   # new selftest, coordq from 862eb518
PASS key-mint
FAIL credit-block: expected (False, False, [True]), got (True, True, [])
$ COORDQ_DIR=$(mktemp -d) heavy python3 coordinator/overnight/selftest.py   # this head
all 26 cases PASS, including credit-block
```

## Merge of origin/main (#703, #704, #705, #715)
Conflicts in `coordinator/bin/coordq` (PROVIDER_BLOCK_SECONDS beside JOURNAL_TITLE_LIMIT), `coordinator/bin/hourly_selftest.py` (EXPECTED has both `credit-block` and `close-evidence`) and `coordinator/overnight/selftest.py` (EVALS has both cases, `close_evidence` body kept from main). Both sides kept.
```
$ COORDQ_DIR=$(mktemp -d) python3 coordinator/overnight/overnight selftest
27 cases PASS, including credit-block and close-evidence
$ COORDQ_DIR=$(mktemp -d) python3 -m unittest tests.test_coordq_action_key tests.test_coordq_capacity tests.test_coordq_message_dedupe tests.test_ticket_gate_live tests.test_ticket_section_headings tests.test_ticket_text_blockers
Ran 162 tests in 27.154s
OK
$ git diff origin/main...HEAD --stat
coordinator/bin/coordq, coordinator/bin/hourly_selftest.py, coordinator/overnight/selftest.py, evidence/MO-722/*
```
