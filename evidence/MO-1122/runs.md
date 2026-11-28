# MO-1122 proof runs

Proof command: the heredoc in the ticket body, run from the repo root (fake gh, 1 s per repo, last repo fails). The machine load average was about 12 during both runs.

## origin/main (bd07679b)
```
FAIL elapsed=14.6s rc=1 failed=None
```

## head
```
PASS elapsed=3.2s rc=0 failed=['digitized/Concerning']
```

## Gateway mark (added)

The gh gateway marked its calls by setting `COORDINATOR_GH_VIA` in `os.environ` around each launch. With threads that races and can leave the mark set. The mark now goes in each call's own `env`, so nothing global is set.
