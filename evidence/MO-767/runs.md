# MO-767 proof runs

Proof command:

    python3 -c "import runpy; g=runpy.run_path('coordinator/bin/ticket'); print(g['builder_bar_section']().splitlines()[0][:24])"

Before (origin/main 04af24c1):

    KeyError: 'builder_bar_section'

After (branch):

    Severity bar (Shyam, 202

The ticket quotes `Severity bar (Shyam, 2026`, which is 25 characters; `[:24]` gives the output above.

`len(gate_bar.GATE_BAR)` is 3335 before and after, and the string equals origin/main's `GATE_BAR`.

`bar_visible({})` returns False, so `assemble_brief` output is unchanged by default.
