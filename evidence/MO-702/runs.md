# MO-702 run output

The sandboxed runs the ticket's acceptance asks for. They live here, apart from the check table in check-proof.md.

## Journal lines carry data.title

Code head these runs used: `a429384032d19450288406c078e562f3d1b9e00f`. The check proof in check-proof.md ran on the same head.

A temp queue dir, a temp COORD_JOURNAL_DIR and a stub t3mcp (two live threads) stand in for the live queue, so no real thread is launched. Only `coordq start` ran (its drain launches the item); `coordq dispatch` was not used because it also runs the ticket refill against the real board.

```
$ coordq start {"threadId":"t-x","message":"<omitted>"} --title "fable idle " + 150 x's
started #1
$ coordq start {"threadId":"t-x","message":"b"} --tool t3_thread_bogus --title bogus
refused: tool 't3_thread_bogus' is not dispatchable. Accepted tools: t3_thread_launch, t3_thread_send
$ coordq start {"threadId":"t-y","message":"c"} --title "second send"
started #2
```

Journal lines (slots lines left out). The first title is cut to 120 characters. The message text of the first start appears in no line (0 matches).

```
{"v":1,"ts":1795145944.827872,"event":"enqueued","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-x","item":1,"attempt":null,"kind":"other","data":{"tool":"t3_thread_send","title":"fable idle xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","taskType":null,"modelSelection":null}}
{"v":1,"ts":1795145944.9519749,"event":"launched","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-x","item":1,"attempt":null,"kind":"other","data":{"tool":"t3_thread_send","title":"fable idle xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx","live":2,"reserved":1,"cap":6}}
{"v":1,"ts":1795145945.0267992,"event":"refused","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-x","item":null,"attempt":null,"kind":"other","data":{"tool":"t3_thread_bogus","title":"bogus","reason":"refused: tool 't3_thread_bogus' is not dispatchable. Accepted tools: t3_thread_launch, t3_thread_send"}}
{"v":1,"ts":1795145945.095417,"event":"enqueued","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-y","item":2,"attempt":null,"kind":"other","data":{"tool":"t3_thread_send","title":"second send","taskType":null,"modelSelection":null}}
{"v":1,"ts":1795145945.118338,"event":"launched","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-y","item":2,"attempt":null,"kind":"other","data":{"tool":"t3_thread_send","title":"second send","live":2,"reserved":2,"cap":6}}
```
