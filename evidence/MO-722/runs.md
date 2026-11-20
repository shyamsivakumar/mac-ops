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
