------------------------- MODULE InstallIfBehind -------------------------
EXTENDS Naturals, FiniteSets, TLC

CONSTANT AllowCrash

Firings == {"F1", "F2"}
PCs == {"idle", "locked", "decided", "installing", "observing", "done", "rolledback", "deferred"}
Terminal == {"done", "rolledback", "deferred"}
Holding == {"locked", "decided", "installing", "observing"}

VARIABLES pc, decision, lock, receipt, activeRelease, verified, rollbackSafe
vars == <<pc, decision, lock, receipt, activeRelease, verified, rollbackSafe>>

Installing == {f \in Firings : pc[f] \in {"installing", "observing"}}

Init == /\ pc = [f \in Firings |-> "idle"]
        /\ decision = [f \in Firings |-> "none"]
        /\ lock = "none"
        /\ receipt = "old"
        /\ activeRelease = "old"
        /\ verified = FALSE
        /\ rollbackSafe = TRUE

Release(f) == lock' = IF lock = f THEN "none" ELSE lock

Acquire(f) == /\ pc[f] = "idle"
              /\ lock = "none"
              /\ lock' = f
              /\ pc' = [pc EXCEPT ![f] = "locked"]
              /\ UNCHANGED <<decision, receipt, activeRelease, verified, rollbackSafe>>

LockHeld(f) == /\ pc[f] = "idle"
               /\ lock # "none"
               /\ pc' = [pc EXCEPT ![f] = "deferred"]
               /\ UNCHANGED <<decision, lock, receipt, activeRelease, verified, rollbackSafe>>

Compare(f, d) == /\ pc[f] = "locked"
                 /\ d = IF receipt = "new" THEN "up_to_date" ELSE "install"
                 /\ decision' = [decision EXCEPT ![f] = d]
                 /\ pc' = [pc EXCEPT ![f] = "decided"]
                 /\ UNCHANGED <<lock, receipt, activeRelease, verified, rollbackSafe>>

FinishUpToDate(f) == /\ pc[f] = "decided"
                     /\ decision[f] = "up_to_date"
                     /\ pc' = [pc EXCEPT ![f] = "done"]
                     /\ Release(f)
                     /\ UNCHANGED <<decision, receipt, activeRelease, verified, rollbackSafe>>

GateBlocks(f) == /\ pc[f] = "decided"
                 /\ decision[f] = "install"
                 /\ pc' = [pc EXCEPT ![f] = "deferred"]
                 /\ Release(f)
                 /\ UNCHANGED <<decision, receipt, activeRelease, verified, rollbackSafe>>

GateClear(f) == /\ pc[f] = "decided"
                /\ decision[f] = "install"
                /\ pc' = [pc EXCEPT ![f] = "installing"]
                /\ UNCHANGED <<decision, lock, receipt, activeRelease, verified, rollbackSafe>>

Install(f) == /\ pc[f] = "installing"
              /\ receipt' = "new"
              /\ activeRelease' = "new"
              /\ verified' = FALSE
              /\ pc' = [pc EXCEPT ![f] = "observing"]
              /\ UNCHANGED <<decision, lock, rollbackSafe>>

ObservePass(f) == /\ pc[f] = "observing"
                  /\ verified' = TRUE
                  /\ pc' = [pc EXCEPT ![f] = "done"]
                  /\ Release(f)
                  /\ UNCHANGED <<decision, receipt, activeRelease, rollbackSafe>>

ObserveFail(f) == /\ pc[f] = "observing"
                  /\ receipt' = "old"
                  /\ activeRelease' = "old"
                  /\ verified' = FALSE
                  /\ rollbackSafe' = (activeRelease' = "old" /\ receipt' = "old")
                  /\ pc' = [pc EXCEPT ![f] = "rolledback"]
                  /\ Release(f)
                  /\ UNCHANGED decision

Crash(f) == /\ AllowCrash
            /\ pc[f] \in Holding
            /\ pc' = [pc EXCEPT ![f] = "idle"]
            /\ decision' = [decision EXCEPT ![f] = "none"]
            /\ Release(f)
            /\ UNCHANGED <<receipt, activeRelease, verified, rollbackSafe>>

Step(f) == \/ Acquire(f) \/ LockHeld(f) \/ (\E d \in {"install", "up_to_date"} : Compare(f, d))
           \/ FinishUpToDate(f) \/ GateBlocks(f) \/ GateClear(f)
           \/ Install(f) \/ ObservePass(f) \/ ObserveFail(f)

Next == \E f \in Firings : Step(f) \/ Crash(f)

Spec == /\ Init /\ [][Next]_vars
        /\ \A f \in Firings : WF_vars(Step(f))

TypeOK == /\ pc \in [Firings -> PCs]
          /\ decision \in [Firings -> {"none", "install", "up_to_date"}]
          /\ lock \in Firings \cup {"none"}
          /\ receipt \in {"old", "new"}
          /\ activeRelease \in {"old", "new"}
          /\ verified \in BOOLEAN
          /\ rollbackSafe \in BOOLEAN

OneInstallerAtATime == Cardinality(Installing) <= 1
NoUnverifiedAccepted == \A f \in Firings :
    (decision[f] = "up_to_date" /\ pc[f] \in {"decided", "done"} /\ receipt = "new") => verified
RollbackRestoresOld == rollbackSafe
EventuallySettled == <>(\A f \in Firings : pc[f] \in Terminal)
=============================================================================
