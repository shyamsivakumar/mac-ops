---- MODULE BoardFloor ----
EXTENDS Naturals, FiniteSets, TLC

CONSTANTS Policy, Environment, Ceiling, InitialLimit,
          AllowRecheckFailure, AllowWriteFailure, AllowStartFailure

ASSUME Policy \in {"legacy", "fixed"}
ASSUME Environment \in {"steady", "warning-alternates", "invalid", "critical", "adversarial"}
ASSUME Ceiling \in {7, 14}
ASSUME InitialLimit \in 0..Ceiling
ASSUME AllowRecheckFailure \in BOOLEAN
ASSUME AllowWriteFailure \in BOOLEAN
ASSUME AllowStartFailure \in BOOLEAN

VARIABLES boardLimit, active, stage, sample, healthyTicks, growthFits,
          warningTurn, warningEpisode, preLimit, activeAtSample,
          pendingTarget, windowReadyAtDecision, recheckPassed,
          tickApplied, jobState, startWasEligible

vars == <<boardLimit, active, stage, sample, healthyTicks, growthFits,
          warningTurn, warningEpisode, preLimit, activeAtSample,
          pendingTarget, windowReadyAtDecision, recheckPassed,
          tickApplied, jobState, startWasEligible>>

InitialActive == 6
Window == 2
Signals == {"healthy", "warning", "critical", "stale", "missing", "bad"}
GoodSignals == {"healthy", "warning"}
BadSignals == {"stale", "missing", "bad"}
Stages == {"start", "sampled", "decided", "rechecked", "done"}
JobStates == {"queued", "started", "failed"}

Min(a, b) == IF a <= b THEN a ELSE b
Max(a, b) == IF a >= b THEN a ELSE b
FloorFor(n) == Min(Ceiling, Max(6, n + 1))
FreshNoncritical == sample \in GoodSignals
FloorAtSample == FloorFor(activeAtSample)

DesiredTarget ==
    IF sample = "critical" THEN 0
    ELSE IF sample \in BadSignals THEN Min(preLimit, activeAtSample)
    ELSE IF Policy = "fixed" /\ FreshNoncritical /\ preLimit < FloorAtSample
         THEN FloorAtSample
    ELSE IF sample = "warning" THEN
         IF preLimit >= FloorAtSample
         THEN Max(FloorAtSample,
                  Min(IF warningEpisode THEN preLimit ELSE preLimit \div 2,
                      activeAtSample))
         ELSE IF preLimit < Min(activeAtSample, FloorAtSample)
              THEN Min(activeAtSample, FloorAtSample)
         ELSE Min(preLimit,
                  IF warningEpisode THEN activeAtSample ELSE preLimit \div 2)
    ELSE IF sample = "healthy" /\ preLimit < FloorAtSample
         THEN IF healthyTicks = Window /\ growthFits
              THEN Min(FloorAtSample, preLimit + 1)
              ELSE preLimit
    ELSE IF sample = "healthy" /\ preLimit < Ceiling
              /\ healthyTicks = Window /\ growthFits
         THEN preLimit + 1
    ELSE preLimit

NextHealthyTicks ==
    IF DesiredTarget > preLimit THEN 0
    ELSE IF sample = "healthy" /\ growthFits
         THEN Min(Window, healthyTicks + 1)
    ELSE 0

NextWarningEpisode ==
    IF sample \in {"warning", "critical"} THEN TRUE
    ELSE IF sample = "healthy" THEN FALSE
    ELSE warningEpisode

SampleChoices ==
    IF Environment = "steady" THEN {"healthy"}
    ELSE IF Environment = "warning-alternates"
         THEN IF warningTurn THEN {"healthy"} ELSE {"warning"}
    ELSE IF Environment = "invalid" THEN BadSignals
    ELSE IF Environment = "critical" THEN {"critical"}
    ELSE Signals

CaptureReading ==
    /\ stage \in {"start", "done"}
    /\ sample' \in SampleChoices
    /\ growthFits' \in (IF Environment \in {"steady", "warning-alternates"}
                         THEN {TRUE} ELSE BOOLEAN)
    /\ activeAtSample' = active
    /\ preLimit' = boardLimit
    /\ pendingTarget' = boardLimit
    /\ stage' = "sampled"
    /\ warningTurn' = ~warningTurn
    /\ windowReadyAtDecision' = FALSE
    /\ recheckPassed' = FALSE
    /\ tickApplied' = FALSE
    /\ UNCHANGED <<boardLimit, active, healthyTicks, warningEpisode,
                    jobState, startWasEligible>>

DecideTarget ==
    /\ stage = "sampled"
    /\ pendingTarget' = DesiredTarget
    /\ windowReadyAtDecision' = (healthyTicks = Window)
    /\ healthyTicks' = NextHealthyTicks
    /\ warningEpisode' = NextWarningEpisode
    /\ stage' = "decided"
    /\ UNCHANGED <<boardLimit, active, sample, growthFits, warningTurn,
                    preLimit, activeAtSample, recheckPassed, tickApplied,
                    jobState, startWasEligible>>

RecheckAccepted ==
    /\ stage = "decided"
    /\ pendingTarget # preLimit
    /\ recheckPassed' = TRUE
    /\ stage' = "rechecked"
    /\ UNCHANGED <<boardLimit, active, sample, healthyTicks, growthFits,
                    warningTurn, warningEpisode, preLimit, activeAtSample,
                    pendingTarget, windowReadyAtDecision, tickApplied,
                    jobState, startWasEligible>>

RecheckRejected ==
    /\ AllowRecheckFailure
    /\ stage = "decided"
    /\ pendingTarget # preLimit
    /\ recheckPassed' = FALSE
    /\ tickApplied' = FALSE
    /\ stage' = "done"
    /\ UNCHANGED <<boardLimit, active, sample, healthyTicks, growthFits,
                    warningTurn, warningEpisode, preLimit, activeAtSample,
                    pendingTarget, windowReadyAtDecision, jobState,
                    startWasEligible>>

RecheckNotNeeded ==
    /\ stage = "decided"
    /\ pendingTarget = preLimit
    /\ recheckPassed' = TRUE
    /\ stage' = "rechecked"
    /\ UNCHANGED <<boardLimit, active, sample, healthyTicks, growthFits,
                    warningTurn, warningEpisode, preLimit, activeAtSample,
                    pendingTarget, windowReadyAtDecision, tickApplied,
                    jobState, startWasEligible>>

WriteSuccess ==
    /\ stage = "rechecked"
    /\ pendingTarget # preLimit
    /\ boardLimit' = pendingTarget
    /\ tickApplied' = TRUE
    /\ stage' = "done"
    /\ UNCHANGED <<active, sample, healthyTicks, growthFits, warningTurn,
                    warningEpisode, preLimit, activeAtSample, pendingTarget,
                    windowReadyAtDecision, recheckPassed, jobState,
                    startWasEligible>>

WriteFailure ==
    /\ AllowWriteFailure
    /\ stage = "rechecked"
    /\ pendingTarget # preLimit
    /\ boardLimit' = preLimit
    /\ tickApplied' = FALSE
    /\ stage' = "done"
    /\ UNCHANGED <<active, sample, healthyTicks, growthFits, warningTurn,
                    warningEpisode, preLimit, activeAtSample, pendingTarget,
                    windowReadyAtDecision, recheckPassed, jobState,
                    startWasEligible>>

NoWriteNeeded ==
    /\ stage = "rechecked"
    /\ pendingTarget = preLimit
    /\ tickApplied' = TRUE
    /\ stage' = "done"
    /\ UNCHANGED <<boardLimit, active, sample, healthyTicks, growthFits,
                    warningTurn, warningEpisode, preLimit, activeAtSample,
                    pendingTarget, windowReadyAtDecision, recheckPassed,
                    jobState, startWasEligible>>

StartQueuedJob ==
    /\ stage = "done"
    /\ tickApplied
    /\ sample \in GoodSignals
    /\ jobState = "queued"
    /\ active < Ceiling
    /\ boardLimit > active
    /\ jobState' = "started"
    /\ active' = active + 1
    /\ startWasEligible' = TRUE
    /\ UNCHANGED <<boardLimit, stage, sample, healthyTicks, growthFits,
                    warningTurn, warningEpisode, preLimit, activeAtSample,
                    pendingTarget, windowReadyAtDecision, recheckPassed,
                    tickApplied>>

StartFailure ==
    /\ AllowStartFailure
    /\ stage = "done"
    /\ tickApplied
    /\ sample \in GoodSignals
    /\ jobState = "queued"
    /\ active < Ceiling
    /\ boardLimit > active
    /\ jobState' = "failed"
    /\ startWasEligible' = FALSE
    /\ UNCHANGED <<boardLimit, active, stage, sample, healthyTicks,
                    growthFits, warningTurn, warningEpisode, preLimit,
                    activeAtSample, pendingTarget, windowReadyAtDecision,
                    recheckPassed, tickApplied>>

Next == CaptureReading \/ DecideTarget \/ RecheckAccepted \/ RecheckRejected
        \/ RecheckNotNeeded \/ WriteSuccess \/ WriteFailure \/ NoWriteNeeded
        \/ StartQueuedJob \/ StartFailure

FairSteps ==
    /\ WF_vars(CaptureReading)
    /\ WF_vars(DecideTarget)
    /\ WF_vars(RecheckAccepted)
    /\ WF_vars(RecheckNotNeeded)
    /\ WF_vars(WriteSuccess)
    /\ WF_vars(NoWriteNeeded)
    /\ SF_vars(StartQueuedJob)

Init ==
    /\ boardLimit = InitialLimit
    /\ active = InitialActive
    /\ stage = "start"
    /\ sample = "missing"
    /\ healthyTicks = 0
    /\ growthFits = FALSE
    /\ warningTurn = FALSE
    /\ warningEpisode = FALSE
    /\ preLimit = InitialLimit
    /\ activeAtSample = InitialActive
    /\ pendingTarget = InitialLimit
    /\ windowReadyAtDecision = FALSE
    /\ recheckPassed = FALSE
    /\ tickApplied = FALSE
    /\ jobState = "queued"
    /\ startWasEligible = FALSE

Spec == Init /\ [][Next]_vars /\ FairSteps

TypeOK ==
    /\ boardLimit \in 0..Ceiling
    /\ active \in InitialActive..Ceiling
    /\ stage \in Stages
    /\ sample \in Signals
    /\ healthyTicks \in 0..Window
    /\ growthFits \in BOOLEAN
    /\ warningTurn \in BOOLEAN
    /\ warningEpisode \in BOOLEAN
    /\ preLimit \in 0..Ceiling
    /\ activeAtSample \in InitialActive..Ceiling
    /\ pendingTarget \in 0..Ceiling
    /\ windowReadyAtDecision \in BOOLEAN
    /\ recheckPassed \in BOOLEAN
    /\ tickApplied \in BOOLEAN
    /\ jobState \in JobStates
    /\ startWasEligible \in BOOLEAN

NoCeilingViolation == boardLimit <= Ceiling

FreshFloorDecision ==
    (stage = "decided" /\ FreshNoncritical /\ preLimit < FloorAtSample)
      => pendingTarget = FloorAtSample

NoRaiseOnInvalid ==
    (stage = "decided" /\ sample \in BadSignals)
      => pendingTarget <= preLimit

AppliedFloor ==
    (stage = "done" /\ tickApplied /\ FreshNoncritical
       /\ preLimit < FloorAtSample)
      => boardLimit = FloorAtSample

AppliedCriticalZero ==
    (stage = "done" /\ tickApplied /\ sample = "critical")
      => boardLimit = 0

AppliedInvalidNoRise ==
    (stage = "done" /\ tickApplied /\ sample \in BadSignals)
      => boardLimit <= preLimit

WarningKeepsFloor ==
    (stage = "decided" /\ sample = "warning" /\ preLimit >= FloorAtSample)
      => pendingTarget >= FloorAtSample

GrowthAboveFloorOneStep ==
    (stage = "decided" /\ pendingTarget > preLimit)
      => \/ /\ preLimit < Min(activeAtSample, FloorAtSample)
           /\ FreshNoncritical
           /\ pendingTarget = Min(activeAtSample, FloorAtSample)
         \/ /\ preLimit >= FloorAtSample
           /\ pendingTarget = preLimit + 1
           /\ sample = "healthy"
           /\ windowReadyAtDecision
           /\ growthFits
         \/ /\ FreshNoncritical /\ preLimit < FloorAtSample
           /\ pendingTarget = FloorAtSample

SafeQueueStart == jobState = "started" => startWasEligible

Safety == /\ TypeOK
          /\ NoCeilingViolation
          /\ FreshFloorDecision
          /\ NoRaiseOnInvalid
          /\ AppliedFloor
          /\ AppliedCriticalZero
          /\ AppliedInvalidNoRise
          /\ WarningKeepsFloor
          /\ GrowthAboveFloorOneStep
          /\ SafeQueueStart

CriticalTickZero ==
    (stage = "done" /\ sample = "critical")
      => (tickApplied /\ boardLimit = 0)

BoardFloorLiveness ==
    []((stage = "sampled" /\ FreshNoncritical /\ preLimit < FloorAtSample)
       => <> (stage = "done" /\ tickApplied /\ boardLimit >= FloorAtSample))

QueueStarts == [] (jobState = "queued" => <> (jobState = "started"))

HealthyWindowRaises ==
    []((stage = "sampled" /\ sample = "healthy"
        /\ preLimit >= FloorAtSample /\ preLimit < Ceiling
        /\ healthyTicks = Window /\ growthFits)
       => <> (stage = "done" /\ tickApplied /\ boardLimit = preLimit + 1))

=============================================================================
