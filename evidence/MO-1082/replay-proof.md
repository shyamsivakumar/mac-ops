# Replay of the two provider errors that killed the builds on 2026-11-17

`python3` with `sys.path` on `coordinator/bin` and a scratch `COORDQ_DIR`, so the
live blocks are neither read nor written.

## GLM 5-hour limit (429 code 1308)

```
builder the ticket names: {"instanceId": "glm", "model": "zai/glm-5.3"}
reason: 1308
blocked provider glm:glm-5.3: 1308
second block line (logged once): None
next builder for the next build: {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"}
```

## MiniMax Token Plan limit (429 code 2056)

```
reason: 2056
blocked provider minimax:MiniMax-M3.1-Flash: 2056
next builder for the next build: {"instanceId": "pi", "model": "deepseek/deepseek-flash"}
```

## The probe waits for the reset, then unblocks after one success

```
probe due at once: False
probe due after one hour: False
probe due after the reset the error named (2 hours): True
probe started: request id builder-probe:glm:1
probe due again an hour after that probe: True
unblocked provider glm:glm-5.3
GLM blocked now: False
builder choice: {"instanceId": "glm", "model": "zai/glm-5.3"}
```
