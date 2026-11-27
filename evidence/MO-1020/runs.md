# MO-1020 runs: `scorecard pareto`

Cost note: the journal records no cost per arm. Cost per ticket lives in the
dispatch receipts and the pi session files (#848 `ticket_costs`). `pareto`
reuses `ticket_costs` and shows median tokens per ticket, because recorded
dollars are 0 on flat plans. With no receipts or thread store the cost is
shown as `unknown`, never 0.

Fixtures come from `evidence/MO-1020/make_fixture.py <dir> [--split|--no-cost]`:
two arms of two tickets each (control 1 of 2 first-gate PASS, 2000 tokens, 2 h;
treatment 2 of 2, 1000 tokens, 1 h).

Proof command (S is the fixture dir, V one of dom, split, nocost):

    COORDQ_DIR=$S/$V/queue T3_STATE_DB=$S/$V/state.sqlite \
      python3 coordinator/bin/scorecard pareto --experiment exp-a --journal-dir $S/$V/journal

Red signature on origin/main: `invalid choice: 'pareto'`.
Green line on this head (dom): `control: ... : dominated by treatment`.

## origin/main

    scorecard: error: argument command: invalid choice: 'pareto' (choose from 'backfill', 'compare')

## head, dom (treatment better on all three)

    control: 2 tickets, quality 50.0%, cost 2000 tokens, latency 2.0 h: dominated by treatment
    treatment: 2 tickets, quality 100.0%, cost 1000 tokens, latency 1.0 h: on the front

## head, split (treatment costs 5000 tokens, so neither dominates)

    control: 2 tickets, quality 50.0%, cost 2000 tokens, latency 2.0 h: on the front
    treatment: 2 tickets, quality 100.0%, cost 5000 tokens, latency 1.0 h: on the front

## head, nocost (no receipts: cost unknown, nothing is marked dominated)

    control: 2 tickets, quality 50.0%, cost unknown, latency 2.0 h: on the front, not comparable (cost unknown)
    treatment: 2 tickets, quality 100.0%, cost unknown, latency 1.0 h: on the front, not comparable (cost unknown)

## compare unchanged (arm_outcomes now also returns the ticket key)

    control: 2 tickets in 2 clusters, first-gate PASS 50.0%
    treatment: 2 tickets in 2 clusters, first-gate PASS 100.0%
    gap +50.0 points, cluster-bootstrap p 0.4839 (4000 draws, seed 7)
    time to merge median: control 7200.0, treatment 3600.0, non-inferior
    no difference
