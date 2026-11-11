------------------------- MODULE InstallIfBehind -------------------------
EXTENDS Naturals, FiniteSets, TLC

CONSTANT AllowCrash

Firings == {"F1", "F2"}
PCs == {"idle", "locked", "decided", "installing", "observing", "done", "rolledback", "deferred"}
Terminal == {"done", "rolledback", "deferred"}
Holding == {"locked", "decided", "installing", "observing"}

VARIABLES pc, decision, lock, receipt, activeRelease, verified, rollbackSafe, marker
vars == <<pc, decision, lock, receipt, activeRelease, verified, rollbackSafe, marker>>

Installing == {f \in Firings : pc[f] \in {"installing", "observing"}}

Init == /\ pc = [f \in Firings |-> "idle"]
        /\ decision = [f \in Firings |-> "none"]
        /\ lock = "none"
        /\ receipt = "old"
        /\ activeRelease = "old"
        /\ verified = FALSE
        /\ rollbackSafe = TRUE
        /\ marker = "none"

Release(f) == lock' = IF lock = f THEN "none" ELSE lock

Acquire(f) == /\ pc[f] = "idle"
               /\ lock = "none"
               /\ lock' = f
               /\ pc' = [pc EXCEPT ![f] = "locked"]
               /\ UNCHANGED <<decision, receipt, activeRelease, verified, rollbackSafe, marker>>

LockHeld(f) == /\ pc[f] = "idle"
                /\ lock # "none"
                /\ pc' = [pc EXCEPT ![f] = "deferred"]
                /\ UNCHANGED <<decision, lock, receipt, activeRelease, verified, rollbackSafe, marker>>

Decision(r, m) ==
    IF ((r = "new") /\ (m = "pending")) THEN "resume"
    ELSE IF (r = "new") THEN "up_to_date" ELSE "install"

Compare(f, d) == /\ pc[f] = "locked"
              /\ d = Decision(receipt, marker)
              /\ decision' = [decision EXCEPT ![f] = d]
              /\ pc' = [pc EXCEPT ![f] = "decided"]
              /\ UNCHANGED <<lock, receipt, activeRelease, verified, rollbackSafe, marker>>

FinishUpToDate(f) == /\ pc[f] = "decided"
                      /\ decision[f] = "up_to_date"
                      /\ pc' = [pc EXCEPT ![f] = "done"]
                      /\ Release(f)
                      /\ UNCHANGED <<decision, receipt, activeRelease, verified, rollbackSafe, marker>>

GateBlocks(f) == /\ pc[f] = "decided"
                 /\ decision[f] = "install"
                 /\ pc' = [pc EXCEPT ![f] = "deferred"]
                 /\ Release(f)
                 /\ UNCHANGED <<decision, lock, receipt, activeRelease, verified, rollbackSafe, marker>>

GateClear(f) == /\ pc[f] = "decided"
                /\ decision[f] = "install"
                /\ pc' = [pc EXCEPT ![f] = "installing"]
                /\ marker' = "pending"
                /\ UNCHANGED <<decision, lock, receipt, activeRelease, verified, rollbackSafe>>

Install(f) == /\ pc[f] = "installing"
              /\ receipt' = "new"
              /\ activeRelease' = "new"
              /\ verified' = FALSE
              /\ marker' = "pending"
              /\ pc' = [pc EXCEPT ![f] = "observing"]
              /\ UNCHANGED <<decision, lock, rollbackSafe>>

Resume(f) == /\ pc[f] = "decided"
            /\ decision[f] = "resume"
            /\ pc' = [pc EXCEPT ![f] = "observing"]
            /\ UNCHANGED <<decision, lock, receipt, activeRelease, verified, rollbackSafe, marker>>

ObservePass(f) == /\ pc[f] = "observing"
                    /\ verified' = TRUE
                    /\ marker' = "none"
                    /\ pc' = [pc EXCEPT ![f] = "done"]
                    /\ Release(f)
                    /\ UNCHANGED <<decision, receipt, activeRelease, rollbackSafe>>

ObserveFail(f) == /\ pc[f] = "observing"
                   /\ receipt' = "old"
                   /\ activeRelease' = "old"
                   /\ verified' = FALSE
                   /\ marker' = "none"
                   /\ rollbackSafe' = (activeRelease' = "old" /\ receipt' = "old")
                   /\ pc' = [pc EXCEPT ![f] = "rolledback"]
                   /\ Release(f)
                   /\ UNCHANGED decision

Crash(f) == /\ AllowCrash
            /\ pc[f] \in Holding
            /\ pc' = [pc EXCEPT ![f] = "idle"]
            /\ decision' = [decision EXCEPT ![f] = "none"]
            /\ Release(f)
            /\ UNCHANGED <<receipt, activeRelease, verified, rollbackSafe, marker>>

TypeOK == /\ pc \in [Firings -> PCs]
          /\ decision \in [Firings -> {"none", "install", "up_to_date", "resume"}]
          /\ lock \in Firings \cup {"none"}
          /\ receipt \in {"old", "new"}
          /\ activeRelease \in {"old", "new"}
          /\ verified \in BOOLEAN
          /\ rollbackSafe \in BOOLEAN
          /\ marker \in {"none", "pending"}

OneInstallerAtATime == Cardinality(Installing) <= 1
NoUnverifiedAccepted == \A f \in Firings :
    (decision[f] = "up_to_date" /\ pc[f] \in {"decided", "done"} /\ receipt = "new") => verified
PendingBlocksAcceptance == \A f \in Firings : (decision[f] = "up_to_date") => (marker = "none")
RollbackRestoresOld == rollbackSafe
EventuallySettled == <>(\A f \in Firings : pc[f] \in Terminal)

Step(f) == \/ Acquire(f) \/ LockHeld(f) \/ (\E d \in {"install", "up_to_date", "resume"} : Compare(f, d))
          \/ FinishUpToDate(f) \/ GateBlocks(f) \/ GateClear(f)
          \/ Install(f) \/ Resume(f) \/ ObservePass(f) \/ ObserveFail(f)

Next == \E f \in Firings : Step(f) \/ Crash(f)

Spec == /\ Init /\ [][Next]_vars
        /\ \A f \in Firings : WF_vars(Step(f))

=============================================================================
