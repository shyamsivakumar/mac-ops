# Swarm trial runbook (Amp Orbs)

This page lists the gates for an Amp Orbs swarm trial and how to stop it.
Nothing here starts Amp. `coordq` has a local spend report and kill switch.

## Gates that remain

All five must hold before the first run.

1. Shyam says yes in writing, in the thread that starts the trial.
2. The cap is $25 and 7 days. In the queue `config.json`, set
   `trials.<name>.capUsd` to 25 and `trials.<name>.days` to 7.
3. Amp uses Push to Branch as the Amp bot. It never pushes to `main` or merges.
4. Touch only mac-ops: no other repo, nothing under `~/Code/slash-eureka`.
5. The kill switch is off. Run `coordq kill status` once to confirm it reads.

## Record the runs

Each run appends one line to `trial-runs.jsonl` in the queue dir:

```json
{"trial": "<name>", "run": "<id>", "tokens": 1200, "cost_usd": 3.5, "at": 1795000000}
```

`cost_usd` is optional. Without it, a run's tokens still count.
It is listed under `runsWithoutCost`.

## Read the spend

```sh
coordq spend --trial <name> --report
```

The report is one JSON line with these values: kill switch state, cap, days,
runs, tokens, dollars, and day of the trial.
A value with no data prints as `"unknown"`, never 0.
With no run file, runs, tokens, and dollars are all `"unknown"`.
`overCap` is true when the dollars reach `capUsd`.
If `overCap` is true or `dayOfTrial` exceeds `days`, flip the kill switch.

## Flip the kill switch

```sh
coordq kill on       # no new work starts
coordq kill off      # new work may start again
coordq kill status   # prints on or off
```

The switch is the file `kill.switch` in the queue dir.

- While on, `coordq dispatch` and refill start nothing. Running work continues.
- `coordq spend` prints that the switch is on.
- A file that exists but cannot be read counts as on.
- Stopping running work is a separate step: interrupt the thread by hand.

## After the trial

Run `coordq kill on` and read the final report.
Put the numbers in the trial's evidence folder.
