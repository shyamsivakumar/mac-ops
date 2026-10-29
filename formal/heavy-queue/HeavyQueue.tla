-------------------------- MODULE HeavyQueue --------------------------
EXTENDS Naturals, FiniteSets, TLC

Jobs == {"deploy", "review", "ordinary"}
States == {"queued", "admitted", "running", "finished", "timedout", "killed"}
VARIABLES state, slots, staleLock, lastAdmissionSafe, lastPrioritySafe, lastDeploySafe, dropSafe
vars == <<state, slots, staleLock, lastAdmissionSafe, lastPrioritySafe, lastDeploySafe, dropSafe>>

Active == {j \in Jobs : state[j] \in {"admitted", "running"}}
Queued == {j \in Jobs : state[j] = "queued"}
Priority(j) == IF j = "review" THEN 0 ELSE IF j = "deploy" THEN 1 ELSE 2
Head(j) == /\ j \in Queued
           /\ \A k \in Queued : Priority(j) <= Priority(k)

Init == /\ state = [j \in Jobs |-> "queued"]
        /\ slots = 1
        /\ staleLock \in BOOLEAN
        /\ lastAdmissionSafe = TRUE
        /\ lastPrioritySafe = TRUE
        /\ lastDeploySafe = TRUE
        /\ dropSafe = TRUE

Admit(j) == /\ Head(j)
            /\ Cardinality(Active) < slots
            /\ state' = [state EXCEPT ![j] = "admitted"]
            /\ lastAdmissionSafe' = (Cardinality(Active) < slots)
            /\ lastPrioritySafe' = (j = "review" \/ "review" \notin Queued)
            /\ lastDeploySafe' = (j = "deploy" \/ "deploy" \notin Queued)
            /\ UNCHANGED <<slots, staleLock, dropSafe>>

Start(j) == /\ state[j] = "admitted"
            /\ state' = [state EXCEPT ![j] = "running"]
            /\ UNCHANGED <<slots, staleLock, lastAdmissionSafe, lastPrioritySafe, lastDeploySafe, dropSafe>>

End(j, result) == /\ state[j] = "running"
                  /\ state' = [state EXCEPT ![j] = result]
                  /\ UNCHANGED <<slots, staleLock, lastAdmissionSafe, lastPrioritySafe, lastDeploySafe, dropSafe>>

Timeout(j) == /\ state[j] = "queued"
              /\ state' = [state EXCEPT ![j] = "timedout"]
              /\ UNCHANGED <<slots, staleLock, lastAdmissionSafe, lastPrioritySafe, lastDeploySafe, dropSafe>>

Capacity(n) == /\ n \in 0..2
               /\ n # slots
               /\ slots' = n
               /\ UNCHANGED <<state, staleLock, lastAdmissionSafe, lastPrioritySafe, lastDeploySafe>>
               /\ dropSafe' = IF n < slots THEN state' = state ELSE TRUE

Next == \/ \E j \in Jobs : Admit(j) \/ Start(j) \/ Timeout(j) \/ (\E r \in {"finished", "killed"} : End(j, r))
        \/ \E n \in 0..2 : Capacity(n)

Spec == /\ Init /\ [][Next]_vars
        /\ \A j \in Jobs : WF_vars(Admit(j)) /\ WF_vars(Start(j))
        /\ \A j \in Jobs : WF_vars(\E r \in {"finished", "killed"} : End(j, r))

TypeOK == /\ state \in [Jobs -> States] /\ slots \in 0..2 /\ staleLock \in BOOLEAN
AdmissionCapacity == lastAdmissionSafe
ReviewerPriority == lastPrioritySafe
DeployPriority == lastDeploySafe
SlotDropDoesNotKill == dropSafe
StaleLockDoesNotBlock == \A j \in Jobs : (staleLock /\ Head(j) /\ Cardinality(Active) < slots) => ENABLED Admit(j)
EventuallyAdmitted == \A j \in Jobs : ((<>[] (slots > 0)) /\ ([] (state[j] # "timedout"))) => <> (state[j] # "queued")
=============================================================================
