--------------------------- MODULE ResumeRetry ---------------------------
EXTENDS Naturals
CONSTANT LoseFailure
VARIABLES paused, pending, physicallyStopped, done, resumeCount
vars == <<paused, pending, physicallyStopped, done, resumeCount>>

Init == /\ paused = TRUE /\ pending = FALSE
        /\ physicallyStopped = TRUE /\ done = FALSE /\ resumeCount = 0

PersistFailedCensusResume ==
    /\ paused /\ physicallyStopped
    /\ paused' = FALSE
    /\ pending' = ~LoseFailure
    /\ UNCHANGED <<physicallyStopped, done, resumeCount>>

PersistSuccessfulCensusResume ==
    /\ paused /\ physicallyStopped
    /\ paused' = FALSE /\ pending' = FALSE
    /\ physicallyStopped' = FALSE /\ done' = TRUE
    /\ resumeCount' = resumeCount + 1

Retry ==
    /\ pending /\ physicallyStopped
    /\ pending' = FALSE /\ physicallyStopped' = FALSE /\ done' = TRUE
    /\ resumeCount' = resumeCount + 1
    /\ UNCHANGED paused

Idle == done /\ UNCHANGED vars
Next == PersistFailedCensusResume \/ PersistSuccessfulCensusResume \/ Retry \/ Idle
Spec == Init /\ [][Next]_vars /\ WF_vars(PersistFailedCensusResume \/ PersistSuccessfulCensusResume) /\ WF_vars(Retry)
Tracked == physicallyStopped => (paused \/ pending)
NoDoubleCompletion == resumeCount <= 1
EventuallyResumed == <>done
=============================================================================
