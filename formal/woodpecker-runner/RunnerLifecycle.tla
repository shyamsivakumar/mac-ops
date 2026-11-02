---------------------------- MODULE RunnerLifecycle ----------------------------
\* Sources: woodpecker v3.16.0 server/queue/fifo.go resubmitExpiredPipelines
\* (expired lease goes to the front of pending; backup is not restored),
\* server/queue/persistent.go Poll (TaskDelete on first poll; absent backup
\* drops the task instead of handing it to another worker),
\* server/rpc/rpc.go Done (UpdateWorkflowStatusToDone before queue ack;
\* fifo.finished does not check which worker owns the lease),
\* agent/runner.go (cancel arrives only through the Wait stream),
\* mac-ops woodpecker-ci scripts/bootstrap.sh (no rollback).
EXTENDS Naturals, FiniteSets

CONSTANTS Workers, Tasks, Partition, StaleDrop, Rollback, MaxFaults

None == "none"

VARIABLES pending, running, exec, db, backup, agentUp, release, install, newBroken, faults

vars == <<pending, running, exec, db, backup, agentUp, release, install, newBroken, faults>>

TypeOK ==
    /\ pending \subseteq Tasks
    /\ running \in [Tasks -> Workers \cup {None}]
    /\ exec \in [Workers -> Tasks \cup {None}]
    /\ db \in [Tasks -> {"pending", "running", "success", "killed"}]
    /\ backup \subseteq Tasks
    /\ agentUp \in BOOLEAN
    /\ release \in {"old", "new"}
    /\ install \in {"idle", "installing", "failed", "rolledback", "done"}
    /\ newBroken \in BOOLEAN
    /\ faults \in 0..MaxFaults

Init ==
    /\ pending = Tasks
    /\ running = [t \in Tasks |-> None]
    /\ exec = [w \in Workers |-> None]
    /\ db = [t \in Tasks |-> "pending"]
    /\ backup = Tasks
    /\ agentUp = TRUE
    /\ release = "old"
    /\ install = "idle"
    /\ newBroken = FALSE
    /\ faults = 0

\* With StaleDrop (persistent queue) a task may be assigned only while its
\* TaskStore backup row still exists. The first successful poll deletes it.
\* Bare FIFO (StaleDrop = FALSE) skips that guard.
Poll(w, t) ==
    /\ agentUp
    /\ exec[w] = None
    /\ t \in pending
    /\ (~StaleDrop \/ t \in backup)
    /\ pending' = pending \ {t}
    /\ backup' = backup \ {t}
    /\ running' = [running EXCEPT ![t] = w]
    /\ exec' = [exec EXCEPT ![w] = t]
    /\ db' = [db EXCEPT ![t] = "running"]
    /\ UNCHANGED <<agentUp, release, install, newBroken, faults>>

\* RPC.Done always writes the workflow DB status, then acknowledges the queue.
\* fifo.finished does not require the reporting worker to still hold the lease:
\* if the task is running it is closed; otherwise it is removed from pending.
Finish(w) ==
    /\ exec[w] # None
    /\ LET t == exec[w] IN
        /\ exec' = [exec EXCEPT ![w] = None]
        /\ db' = [db EXCEPT ![t] = "success"]
        /\ IF running[t] = w
              THEN /\ running' = [running EXCEPT ![t] = None]
                   /\ pending' = pending
              ELSE /\ pending' = pending \ {t}
                   /\ UNCHANGED running
    /\ UNCHANGED <<backup, agentUp, release, install, newBroken, faults>>

\* Resubmit restores the in-memory pending entry only. The TaskStore backup
\* is not re-inserted (matches resubmitExpiredPipelines + persistentQueue).
Resubmit(t) ==
    /\ pending' = pending \cup {t}
    /\ running' = [running EXCEPT ![t] = None]
    /\ UNCHANGED <<exec, db, backup, agentUp, release, install, newBroken>>

LeaseExpire(t) ==
    /\ running[t] # None
    /\ exec[running[t]] # t
    /\ Resubmit(t)
    /\ UNCHANGED faults

LeasePartition(t) ==
    /\ Partition
    /\ faults < MaxFaults
    /\ running[t] # None
    /\ exec[running[t]] = t
    /\ Resubmit(t)
    /\ faults' = faults + 1

CancelDeliver(w) ==
    /\ exec[w] # None
    /\ running[exec[w]] # w
    /\ exec' = [exec EXCEPT ![w] = None]
    /\ UNCHANGED <<pending, running, db, backup, agentUp, release, install, newBroken, faults>>

\* persistentQueue.Poll: task is in pending after resubmit, backup row gone,
\* so the server drops it instead of assigning it again.
StaleDropAct(t) ==
    /\ StaleDrop
    /\ t \in pending
    /\ t \notin backup
    /\ pending' = pending \ {t}
    /\ UNCHANGED <<running, exec, db, backup, agentUp, release, install, newBroken, faults>>

AgentRestart ==
    /\ agentUp
    /\ install \in {"idle", "done", "rolledback"}
    /\ faults < MaxFaults
    /\ exec' = [w \in Workers |-> None]
    /\ faults' = faults + 1
    /\ UNCHANGED <<pending, running, db, backup, agentUp, release, install, newBroken>>

InstallStart ==
    /\ install = "idle"
    /\ faults < MaxFaults
    /\ agentUp' = FALSE
    /\ exec' = [w \in Workers |-> None]
    /\ release' = "new"
    /\ install' = "installing"
    /\ \E b \in BOOLEAN : newBroken' = b
    /\ faults' = faults + 1
    /\ UNCHANGED <<pending, running, db, backup>>

InstallUp ==
    /\ install = "installing"
    /\ IF newBroken
          THEN install' = "failed" /\ agentUp' = FALSE
          ELSE install' = "done" /\ agentUp' = TRUE
    /\ UNCHANGED <<pending, running, exec, db, backup, release, newBroken, faults>>

RollbackAct ==
    /\ Rollback
    /\ install = "failed"
    /\ release' = "old"
    /\ agentUp' = TRUE
    /\ install' = "rolledback"
    /\ UNCHANGED <<pending, running, exec, db, backup, newBroken, faults>>

Stutter == UNCHANGED vars

Next ==
    \/ \E w \in Workers, t \in Tasks : Poll(w, t)
    \/ \E w \in Workers : Finish(w)
    \/ \E t \in Tasks : LeaseExpire(t)
    \/ \E t \in Tasks : LeasePartition(t)
    \/ \E w \in Workers : CancelDeliver(w)
    \/ \E t \in Tasks : StaleDropAct(t)
    \/ AgentRestart
    \/ InstallStart
    \/ InstallUp
    \/ RollbackAct
    \/ Stutter

Spec == Init /\ [][Next]_vars

LiveSpec ==
    /\ Spec
    /\ WF_vars(\E w \in Workers, t \in Tasks : Poll(w, t))
    /\ WF_vars(\E w \in Workers : Finish(w))
    /\ WF_vars(\E t \in Tasks : LeaseExpire(t))
    /\ WF_vars(\E w \in Workers : CancelDeliver(w))
    /\ WF_vars(\E t \in Tasks : StaleDropAct(t))
    /\ WF_vars(InstallUp)
    /\ WF_vars(RollbackAct)

RunnerAlwaysUp == agentUp

NoDoubleRun == \A t \in Tasks : Cardinality({w \in Workers : exec[w] = t}) <= 1

RunnerComesBack == [](install = "failed" => <>agentUp)

FailedInstallRollsBack == install = "failed" ~> install = "rolledback"

JobsReported == \A t \in Tasks : db[t] = "running" ~> db[t] \in {"success", "killed"}

=============================================================================
