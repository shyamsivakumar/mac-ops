# MO-767 proof runs

Proof command:

    python3 -c "import runpy; g=runpy.run_path('coordinator/bin/ticket'); print(g['builder_bar_section']().splitlines()[0][:24])"

Before (origin/main 8c0b1568):

    KeyError: 'builder_bar_section'

After (branch):

    Severity bar (Shyam, 202

The ticket quotes `Severity bar (Shyam, 2026`, which is 25 characters; `[:24]` gives the output above.

GATE_BAR length (`gate_bar.GATE_BAR`): 3335 before, 3335 after. The string is also equal to origin/main's GATE_BAR (`==` is True).

`bar_visible({})` returns False, so `assemble_brief` output is unchanged by default.
