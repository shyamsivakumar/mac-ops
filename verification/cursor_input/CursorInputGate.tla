-------------------------- MODULE CursorInputGate --------------------------
EXTENDS Naturals, TLC
CONSTANT GuardWritten
VARIABLES ready, havePaste, queued, remaining, written, echo, ticks,
          enterReceived, released, entered, closed, cancelled, sendCount
vars == <<ready, havePaste, queued, remaining, written, echo, ticks,
          enterReceived, released, entered, closed, cancelled, sendCount>>
Init == /\ ready = FALSE /\ havePaste = FALSE /\ queued = FALSE
        /\ remaining = 0 /\ written = FALSE /\ echo = FALSE /\ ticks = 0
        /\ enterReceived = FALSE /\ released = FALSE /\ entered = FALSE
        /\ closed = FALSE /\ cancelled = FALSE /\ sendCount = 0
Ready == /\ ~closed /\ ~ready /\ ready' = TRUE
         /\ UNCHANGED <<havePaste, queued, remaining, written, echo, ticks,
                        enterReceived, released, entered, closed, cancelled, sendCount>>
Paste == /\ ~closed /\ ~havePaste /\ havePaste' = TRUE
         /\ UNCHANGED <<ready, queued, remaining, written, echo, ticks,
                        enterReceived, released, entered, closed, cancelled, sendCount>>
Queue == /\ ~closed /\ ready /\ havePaste /\ ~queued
         /\ queued' = TRUE /\ remaining' = 2
         /\ UNCHANGED <<ready, havePaste, written, echo, ticks,
                        enterReceived, released, entered, closed, cancelled, sendCount>>
Write == /\ ~closed /\ queued /\ remaining > 0
         /\ remaining' = remaining - 1
         /\ written' = (remaining = 1)
         /\ UNCHANGED <<ready, havePaste, queued, echo, ticks,
                        enterReceived, released, entered, closed, cancelled, sendCount>>
Echo == /\ ~closed /\ ~echo
        /\ (IF GuardWritten THEN written ELSE (queued /\ remaining = 1))
        /\ echo' = TRUE
        /\ UNCHANGED <<ready, havePaste, queued, remaining, written, ticks,
                       enterReceived, released, entered, closed, cancelled, sendCount>>
Tick == /\ ~closed /\ echo /\ ticks < 3 /\ ticks' = ticks + 1
        /\ UNCHANGED <<ready, havePaste, queued, remaining, written, echo,
                       enterReceived, released, entered, closed, cancelled, sendCount>>
ReceiveEnter == /\ ~closed /\ havePaste /\ ~enterReceived /\ enterReceived' = TRUE
                /\ UNCHANGED <<ready, havePaste, queued, remaining, written, echo, ticks,
                               released, entered, closed, cancelled, sendCount>>
Release == /\ ~closed /\ ready /\ echo /\ ticks = 3 /\ ~released
           /\ (IF GuardWritten THEN written ELSE TRUE)
           /\ released' = TRUE
           /\ UNCHANGED <<ready, havePaste, queued, remaining, written, echo, ticks,
                          enterReceived, entered, closed, cancelled, sendCount>>
SendEnter == /\ ~closed /\ released /\ enterReceived /\ ~entered
             /\ entered' = TRUE /\ sendCount' = sendCount + 1
             /\ UNCHANGED <<ready, havePaste, queued, remaining, written, echo, ticks,
                            enterReceived, released, closed, cancelled>>
Cancel == /\ ~closed /\ ~released /\ closed' = TRUE /\ cancelled' = TRUE
          /\ UNCHANGED <<ready, havePaste, queued, remaining, written, echo, ticks,
                         enterReceived, released, entered, sendCount>>
Timeout == /\ ~closed /\ ~released /\ closed' = TRUE
           /\ UNCHANGED <<ready, havePaste, queued, remaining, written, echo, ticks,
                          enterReceived, released, entered, cancelled, sendCount>>
Idle == UNCHANGED vars
Next == Ready \/ Paste \/ Queue \/ Write \/ Echo \/ Tick \/ ReceiveEnter
        \/ Release \/ SendEnter \/ Cancel \/ Timeout \/ Idle
TypeOK == /\ ready \in BOOLEAN /\ havePaste \in BOOLEAN /\ queued \in BOOLEAN
          /\ remaining \in 0..2 /\ written \in BOOLEAN /\ echo \in BOOLEAN
          /\ ticks \in 0..3 /\ enterReceived \in BOOLEAN /\ released \in BOOLEAN
          /\ entered \in BOOLEAN /\ closed \in BOOLEAN /\ cancelled \in BOOLEAN
          /\ sendCount \in 0..1
ReadyBeforePaste == queued => ready
ReleaseAfterAcknowledgement == released => (ready /\ written /\ echo /\ ticks = 3)
EnterAfterRelease == entered => (released /\ written /\ echo /\ ticks = 3)
CancellationHoldsEnter == cancelled => ~entered
=============================================================================
