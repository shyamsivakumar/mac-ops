# Shadow verdict

A repeat asks a model for one JSON verdict. A non-verdict reply is an error,
excluded from flip and false-block rates. The scorecard never blocks a merge.

```mermaid
stateDiagram-v2
    [*] --> Prompted: a repeat asks the model, or replays the saved review
    Prompted --> TimedOut: the model call exceeds its timeout
    Prompted --> Unparsed: the reply has no top-level verdict object
    Prompted --> ReportedError: the object says error
    Prompted --> PassMissing: the object has no pass field
    Prompted --> Valid: pass is true or false
    TimedOut --> Excluded
    Unparsed --> Excluded
    ReportedError --> Excluded
    PassMissing --> Excluded
    Valid --> Counted: the repeat is kept for flip rate, recall, and false block
```

| State | Event | Guard | Side effect |
| --- | --- | --- | --- |
| Unparsed | model text | no verdict object | error, raw kept to 800 chars |
| ReportedError | parsed object | `error` set | error verdict |
| PassMissing | parsed object | `pass` is null | error verdict |
| TimedOut | subprocess | `TimeoutExpired` | error verdict, raw `timeout` |
| Counted | metrics | `error` is false | enters flip rate, recall, false block |
| Excluded | metrics | `error` is true | in `error_repeats`, not in rates |

Repeats run together, sorted by repeat number. Replays parse the saved review.
