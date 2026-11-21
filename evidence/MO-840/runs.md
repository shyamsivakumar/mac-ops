# MO-840 runs

## Proof command on main
```
KeyError: 'parity_title_ok'
```

## Proof command on the head
```
True False
```

## ticket open --dry-run (temp COORDQ_DIR, COORD_JOURNAL_DIR)

title: Parity 23b · x
```
refused: a Parity title must read `Parity P<digits><letters>[.<digits>] · <title>`, for example `Parity P23b.1 · name`
exit 2
```

title: Parity P23b.1 · x
```
refused: template section 'Goal and why' is missing
exit 2 (passes the title check; stops later at the body check because no body was given)
```
