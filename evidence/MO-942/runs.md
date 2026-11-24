# MO-942 runs

## Red on origin/main (9735d513)
AssertionError: settings
exit 1

## Green on branch
exit 0

## After merge of origin/main and the GLM 5.4 rename
Proof command exit 0

`diff coordinator/pi/settings.json ~/.pi/agent-coordinator/settings.json` (live copy has only the deepseek lines extra):
```
13a14
>     "deepseek/deepseek-flash",
39a41,43
>       "deepseek/deepseek-flash": {
>         "reserveTokens": 32000
>       },
```
