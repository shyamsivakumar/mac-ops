---------------------------- MODULE RestartLatch ----------------------------
\* One board task whose agent has exited. Each action is one watcher tick,
\* or a crash that discards the tick's memory because tick() reads the state
\* file again next time (board_restart.py:303, 438).
EXTENDS Integers

\* Persist FALSE: restarted_exit was replaced before the commands
\* (board_restart.py:395-402), then write_state at the end of tick raised
\* before os.replace (board_restart.py:212-222, called at 438). The
\* controller catches that and the next minute calls tick() on the file
\* that already holds the exit (board_governor.py:1334-1338).
\* Latch FALSE: the restarted_exit guard at board_restart.py:363-364 and the
\* write at 395-396 are absent.
\* Wipe TRUE: a reload erases a latch the code's read_state keeps.
\* BadGuard TRUE: restart even when the state file was rejected or exitedAt
\* is missing. The code refuses both (board_restart.py:204-205, 358-360).
CONSTANTS Persist, Latch, Wipe, BadGuard

VARIABLES
  exit,         \* 0 missing, 1 this death, 2 a later death
  remembered,   \* exit that left the row; task.json does not move exitedAt backward
  badFile,      \* read_state would raise
  phase,        \* "idle" | "seen" | "ready"
  disk,         \* restarted_exit in board-restart.state.json, 0 if unset
  pending,      \* pending_tell is waiting
  up,           \* the pane has a new live agent
  ok1, ok2,     \* successful restart() calls for that exit
  fails,        \* failed restart() calls, which still count toward the cap
  badRestarts,  \* restart() calls with a missing exit or a bad state file
  told,
  lastOk        \* exit id of the last successful persisted-or-not restart

vars == <<exit, remembered, badFile, phase, disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk, remembered>>

Init ==
  /\ exit = 1
  /\ remembered = 0
  /\ badFile = FALSE
  /\ phase = "idle"
  /\ disk = 0
  /\ pending = FALSE
  /\ up = FALSE
  /\ ok1 = 0 /\ ok2 = 0 /\ fails = 0 /\ badRestarts = 0
  /\ told = FALSE
  /\ lastOk = 0

\* board_restart.py:367-368. The code's cap is a rolling hour. This bound is a
\* lifetime cap of three, which is stricter. The second success happens
\* before that cap, so the cap cannot hide a repeated restart.
underCap == ok1 + ok2 + fails + badRestarts < 3

inputOk == badFile = FALSE /\ exit \in {1, 2}

canRestart ==
  /\ phase = "ready"
  /\ underCap
  /\ IF BadGuard
     THEN TRUE
     ELSE /\ inputOk
          \* board_restart.py:363-364
          /\ \/ ~Latch
             \/ disk # exit

\* A restart while the file was rejected or the exit is missing counts as a
\* bad restart even if exit still shows 1 or 2. board_restart.py:204-205, 358-360.
countSuccess ==
  IF ~inputOk THEN badRestarts' = badRestarts + 1 /\ ok1' = ok1 /\ ok2' = ok2
  ELSE IF exit = 1 THEN ok1' = ok1 + 1 /\ ok2' = ok2 /\ badRestarts' = badRestarts
  ELSE IF exit = 2 THEN ok2' = ok2 + 1 /\ ok1' = ok1 /\ badRestarts' = badRestarts
  ELSE badRestarts' = badRestarts + 1 /\ ok1' = ok1 /\ ok2' = ok2

\* First sight of this signature starts the 60s clock. board_restart.py:334-337, 365-366
See ==
  /\ phase = "idle"
  /\ inputOk
  /\ phase' = "seen"
  /\ UNCHANGED <<exit, badFile, disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk, remembered>>

\* A later tick. now - first_seen >= MIN_INTERVAL_SECONDS. board_restart.py:365-366
Age ==
  /\ phase = "seen"
  /\ phase' = "ready"
  /\ UNCHANGED <<exit, badFile, disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk, remembered>>

\* Commands succeeded. The exit is already on disk. Persist TRUE also resets
\* the 60s clock and stores the tell (board_restart.py:404-412, 438).
\* Persist FALSE keeps the exit and drops that later replace.
RestartOk ==
  /\ canRestart
  /\ countSuccess
  /\ fails' = fails
  /\ disk' = IF Latch /\ inputOk /\ exit \in {1, 2} THEN exit ELSE disk
  /\ lastOk' = IF inputOk /\ exit \in {1, 2} THEN exit ELSE lastOk
  /\ pending' = IF Persist THEN TRUE ELSE pending
  /\ phase' = IF Persist THEN "seen" ELSE phase
  /\ UNCHANGED <<exit, badFile, up, told, remembered>>

\* A command failed. The intent is cleared and replaced, and first_seen stays,
\* so the next tick may retry at once. board_restart.py:413-418. Disk returns
\* to the exit saved before this attempt.
RestartFail ==
  /\ canRestart
  /\ IF ~inputOk
     THEN badRestarts' = badRestarts + 1 /\ fails' = fails
     ELSE fails' = fails + 1 /\ badRestarts' = badRestarts
  /\ UNCHANGED <<exit, badFile, phase, disk, pending, up, ok1, ok2, told, lastOk, remembered>>

\* Tell is decided before restart, and it does not clear a saved exit.
\* board_restart.py:323-330
Tell ==
  /\ pending /\ up
  /\ told' = TRUE
  /\ pending' = FALSE
  /\ UNCHANGED <<exit, badFile, phase, disk, up, ok1, ok2, fails, badRestarts, lastOk, remembered>>

AgentUp ==
  /\ up = FALSE
  /\ up' = TRUE
  /\ UNCHANGED <<exit, badFile, phase, disk, pending, ok1, ok2, fails, badRestarts, told, lastOk, remembered>>

\* Same signature, new exitedAt. first_seen is not reset. board_restart.py:334-337
NewDeath ==
  /\ exit = 1
  /\ exit' = 2
  /\ badFile' = FALSE
  /\ UNCHANGED <<phase, disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk, remembered>>

\* The row is no longer a dead agent. restarted_exit stays on the record.
\* board_restart.py:417-421 pops first_seen and signature, not restarted_exit.
GoHealthy ==
  /\ phase' = "idle"
  /\ remembered' = IF exit = 0 THEN remembered ELSE exit
  /\ exit' = 0
  /\ UNCHANGED <<badFile, disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk>>

\* The exit that just left the row is back. exitedAt does not move backward,
\* so this is not an older death. first_seen starts over (334-337) and the
\* saved exit is still compared at 363-364.
Recover ==
  /\ exit = 0
  /\ remembered \in {1, 2}
  /\ exit' = remembered
  /\ badFile' = FALSE
  /\ phase' = "idle"
  /\ UNCHANGED <<remembered, disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk>>

\* exitedAt is not a number. The tick records no_exit_time and does not restart
\* unless BadGuard removes that check. board_restart.py:357-360
Missing ==
  /\ remembered' = IF exit \in {1, 2} THEN exit ELSE remembered
  /\ exit' = 0
  /\ badFile' = FALSE
  /\ phase' = "ready"
  /\ UNCHANGED <<disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk>>

\* read_state raises. main exits and the controller records board_restart_error.
\* board_restart.py:204-205, board_governor.py:1336-1338
Corrupt ==
  /\ badFile' = TRUE
  /\ UNCHANGED <<exit, phase, disk, pending, up, ok1, ok2, fails, badRestarts, told, lastOk, remembered>>

\* A process start that erases the state file. The code's read_state does not.
WipeFile ==
  /\ Wipe
  /\ disk # 0
  /\ disk' = 0
  /\ phase' = "idle"
  /\ pending' = FALSE
  /\ UNCHANGED <<exit, badFile, up, ok1, ok2, fails, badRestarts, told, lastOk, remembered>>

Pause == UNCHANGED vars

SafetyNext ==
  \/ See \/ Age \/ RestartOk \/ RestartFail \/ Tell \/ AgentUp
  \/ NewDeath \/ GoHealthy \/ Recover \/ Missing \/ Corrupt \/ WipeFile \/ Pause

LiveNext == See \/ Age \/ RestartOk \/ AgentUp \/ Tell \/ Pause

\* TLC only treats Init as the initial predicate when it is the first conjunct.
SafetySpec == Init /\ [][SafetyNext]_vars
LiveSpec == Init /\ [][LiveNext]_vars
            /\ WF_vars(See) /\ WF_vars(Age) /\ WF_vars(RestartOk)
            /\ WF_vars(AgentUp) /\ WF_vars(Tell)

TypeOK ==
  /\ exit \in 0..2 /\ remembered \in 0..2 /\ phase \in {"idle", "seen", "ready"}
  /\ badFile \in BOOLEAN /\ pending \in BOOLEAN /\ up \in BOOLEAN /\ told \in BOOLEAN
  /\ disk \in 0..2 /\ lastOk \in 0..2
  /\ ok1 \in 0..3 /\ ok2 \in 0..3 /\ fails \in 0..3 /\ badRestarts \in 0..3

\* A successful restart of one death happens once. The exit is replaced
\* before the commands, so a crash of the later replace still counts once.
NoDoubleSuccess == ok1 <= 1 /\ ok2 <= 1

\* A missing exit or a rejected state file does not call restart().
NoActionOnBadInput == badRestarts = 0

\* The exit written before the commands is still there after the actions
\* that keep the file. Persist FALSE keeps that exit when Latch is on.
SavedLatch == lastOk = 0 \/ disk = lastOk \/ (~Latch /\ ~Persist)

EventuallyRestarted == <>(ok1 = 1)
EventuallyTold == <>told

NotYetRestarted == ok1 = 0
=============================================================================
