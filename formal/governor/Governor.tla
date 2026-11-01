---- MODULE Governor ----
EXTENDS Naturals, FiniteSets, TLC

CONSTANTS Policy, Environment, AllowPublicationFailure, AllowStartFailure,
          AllowRestarts, AllowSignalFailure

ASSUME Policy \in {"legacy", "fixed"}
ASSUME Environment \in {"adversarial", "steady", "missing", "warning-alternates"}
ASSUME AllowPublicationFailure \in BOOLEAN
ASSUME AllowStartFailure \in BOOLEAN
ASSUME AllowRestarts \in BOOLEAN
ASSUME AllowSignalFailure \in BOOLEAN

MaxSlots == {2, 3, 4}
Window == 2
BoardSnapshotActive == 2
Signals == {"healthy", "noise", "warning", "critical", "stale", "missing", "bad"}
BadSignals == {"stale", "missing", "bad"}
GoodSignals == {"healthy", "noise", "warning"}
Stages == {"start", "sampled", "decided", "published", "done"}
Jobs == {"waiting", "reserved", "running", "failed"}
PauseStates == {"none", "requested", "paused", "signal_failed"}

Min(a, b) == IF a <= b THEN a ELSE b
Max(a, b) == IF a >= b THEN a ELSE b
Floor(n) == Min(2, n)

VARIABLES maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
          healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
          stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
          preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
          pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
          pendingWarningEpisode, lastPublishedSample, lastBoardSample,
          lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
          lastBoardFit, lastBoardGrew, publicationSucceeded,
          jobState, eligibleSeen, reservationValid, startedSafely,
          activeAtTick, criticalAtTick, pauseRequested, pauseStatus

vars == <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
          healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
          stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
          preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
          pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
          pendingWarningEpisode, lastPublishedSample, lastBoardSample,
          lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
          lastBoardFit, lastBoardGrew, publicationSucceeded,
          jobState, eligibleSeen, reservationValid, startedSafely,
          activeAtTick, criticalAtTick, pauseRequested, pauseStatus>>

CurrentSlots == IF capacityFresh /\ capacityBoot = boot THEN publishedSlots ELSE 0
ActiveHeavy == IF jobState = "running" THEN 1 ELSE 0
FreshSample == sample \in GoodSignals
EligibleSample == sample = "healthy"

AdaptiveTarget ==
    \* board_governor.py:665-755
    IF sample = "critical" \/ sample = "warning" THEN 0
    ELSE IF sample = "noise" THEN Min(CurrentSlots, ActiveHeavy)
    ELSE IF sample \in BadSignals THEN Min(CurrentSlots, Floor(maxSlots))
    ELSE IF resourceFit < CurrentSlots THEN Min(CurrentSlots \div 2, resourceFit)
    ELSE IF EligibleSample /\ resourceFit >= CurrentSlots + 1
            /\ CurrentSlots < maxSlots /\ healthyTicks = Window
         THEN CurrentSlots + 1
    ELSE CurrentSlots

HeavyTarget ==
    \* board_governor.py:761-780
    IF sample = "critical" THEN 0
    ELSE IF sample \in BadSignals THEN Min(CurrentSlots, Floor(maxSlots))
    ELSE IF Policy = "fixed" THEN Min(maxSlots, Max(Floor(maxSlots), AdaptiveTarget))
    ELSE AdaptiveTarget

NextHealthyTicks ==
    IF sample = "noise" THEN healthyTicks
    ELSE
    IF EligibleSample /\ resourceFit >= CurrentSlots + 1 /\ CurrentSlots < maxSlots
    THEN IF AdaptiveTarget > CurrentSlots THEN 0 ELSE Min(Window, healthyTicks + 1)
    ELSE 0

NextBoardTarget ==
    \* board_governor.py:884-963
    IF sample = "critical" THEN 0
    ELSE IF sample = "warning" THEN
        IF warningEpisode THEN Min(preBoardLimit, BoardSnapshotActive)
        ELSE Min(preBoardLimit \div 2, BoardSnapshotActive)
    ELSE IF EligibleSample /\ boardFit THEN
        IF preBoardLimit > BoardSnapshotActive + 1 THEN BoardSnapshotActive + 1
        ELSE IF preBoardLimit > BoardSnapshotActive THEN preBoardLimit
        ELSE IF boardHealthyTicks = Window
             /\ preBoardLimit + 1 <= BoardSnapshotActive + 1
             THEN preBoardLimit + 1
        ELSE preBoardLimit
    ELSE Min(preBoardLimit, BoardSnapshotActive)

NextBoardHealthyTicks ==
    IF EligibleSample /\ boardFit /\ preBoardLimit <= BoardSnapshotActive
    THEN IF NextBoardTarget > preBoardLimit
         THEN 0
         ELSE Min(Window, boardHealthyTicks + 1)
    ELSE 0

NextWarningEpisode ==
    IF sample = "critical" \/ sample = "warning" THEN TRUE
    ELSE IF EligibleSample /\ boardFit THEN FALSE
    ELSE warningEpisode

Init ==
    /\ maxSlots \in MaxSlots
    /\ boot = 0
    /\ capacityBoot = 0
    /\ capacityFresh = TRUE
    /\ publishedSlots = 0
    /\ healthyTicks = 0
    /\ boardLimit = 2
    /\ boardHealthyTicks = 0
    /\ warningEpisode = FALSE
    /\ stage = "start"
    /\ sample = "missing"
    /\ resourceFit = 0
    /\ boardFit = FALSE
    /\ identityOK = FALSE
    /\ taskSlotFree = FALSE
    /\ preSlots = 0
    /\ preBoardLimit = 2
    /\ preWarningEpisode = FALSE
    /\ pendingTarget = 0
    /\ pendingHealthyTicks = 0
    /\ pendingBoardTarget = 2
    /\ pendingBoardHealthyTicks = 0
    /\ pendingWarningEpisode = FALSE
    /\ lastPublishedSample = "missing"
    /\ lastBoardSample = "missing"
    /\ lastPublishBefore = 0
    /\ lastBoardBefore = 2
    /\ lastBoardWasWarningEpisode = FALSE
    /\ lastBoardFit = FALSE
    /\ lastBoardGrew = FALSE
    /\ publicationSucceeded = FALSE
    /\ jobState = "waiting"
    /\ eligibleSeen = FALSE
    /\ reservationValid = FALSE
    /\ startedSafely = FALSE
    /\ activeAtTick = FALSE
    /\ criticalAtTick = FALSE
    /\ pauseRequested = FALSE
    /\ pauseStatus = "none"

CaptureReading ==
    \* board_governor.py:1048-1068; heavy.py:185-266
    /\ stage \in {"start", "done"}
    /\ sample' \in (IF Environment = "steady" THEN {"healthy"}
                     ELSE IF Environment = "missing" THEN {"missing"}
                     ELSE IF Environment = "warning-alternates"
                          THEN IF warningEpisode THEN {"healthy"} ELSE {"warning"}
                          ELSE Signals)
    /\ (sample' = "noise" => sample # "noise")
    /\ resourceFit' \in (IF Environment \in {"steady", "warning-alternates"}
                          THEN {maxSlots}
                          ELSE {0, CurrentSlots,
                                Min(CurrentSlots + 1, maxSlots), maxSlots})
    /\ boardFit' \in (IF Environment \in {"steady", "warning-alternates"}
                       THEN {TRUE} ELSE BOOLEAN)
    /\ identityOK' \in (IF Environment \in {"steady", "warning-alternates"}
                         THEN {TRUE} ELSE BOOLEAN)
    /\ taskSlotFree' \in (IF Environment \in {"steady", "warning-alternates"}
                           THEN {TRUE} ELSE BOOLEAN)
    /\ preSlots' = CurrentSlots
    /\ preBoardLimit' = boardLimit
    /\ preWarningEpisode' = warningEpisode
    /\ pendingTarget' = CurrentSlots
    /\ pendingHealthyTicks' = healthyTicks
    /\ pendingBoardTarget' = boardLimit
    /\ pendingBoardHealthyTicks' = boardHealthyTicks
    /\ pendingWarningEpisode' = warningEpisode
    /\ lastPublishedSample' = "missing"
    /\ lastPublishBefore' = publishedSlots
    /\ lastBoardSample' = "missing"
    /\ lastBoardBefore' = boardLimit
    /\ lastBoardWasWarningEpisode' = FALSE
    /\ lastBoardFit' = FALSE
    /\ lastBoardGrew' = FALSE
    /\ activeAtTick' = (jobState = "running")
    /\ criticalAtTick' = (sample' = "critical")
    /\ stage' = "sampled"
    /\ publicationSucceeded' = FALSE
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    jobState, eligibleSeen, reservationValid, startedSafely,
                    pauseRequested, pauseStatus>>

DecideTargets ==
    \* board_governor.py:605-780; board_governor.py:810-983
    /\ stage = "sampled"
    /\ pendingTarget' = HeavyTarget
    /\ pendingHealthyTicks' = NextHealthyTicks
    /\ pendingBoardTarget' = NextBoardTarget
    /\ pendingBoardHealthyTicks' = NextBoardHealthyTicks
    /\ pendingWarningEpisode' = NextWarningEpisode
    /\ stage' = "decided"
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode,
                    lastPublishedSample, lastBoardSample, lastPublishBefore,
                    lastBoardBefore, lastBoardWasWarningEpisode, lastBoardFit,
                    lastBoardGrew, publicationSucceeded, jobState, eligibleSeen,
                    reservationValid, startedSafely, activeAtTick, criticalAtTick,
                    pauseRequested, pauseStatus>>

PublishCapacity ==
    \* board_governor.py:1064-1071; board_governor.py:1090-1091
    /\ stage = "decided"
    /\ publishedSlots' = pendingTarget
    /\ capacityFresh' = TRUE
    /\ capacityBoot' = boot
    /\ healthyTicks' = pendingHealthyTicks
    /\ lastPublishedSample' = sample
    /\ lastPublishBefore' = preSlots
    /\ publicationSucceeded' = TRUE
    /\ stage' = "published"
    /\ UNCHANGED <<maxSlots, boot, boardLimit, boardHealthyTicks, warningEpisode,
                    sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastBoardSample, lastBoardBefore,
                    lastBoardWasWarningEpisode, lastBoardFit, lastBoardGrew,
                    jobState, eligibleSeen, reservationValid, startedSafely,
                    activeAtTick, criticalAtTick, pauseRequested, pauseStatus>>

CensusFailure ==
    \* board_governor.py:1265-1292
    /\ Environment = "adversarial"
    /\ stage = "sampled"
    /\ publishedSlots' = IF sample = "critical" THEN 0
                         ELSE IF FreshSample THEN Floor(maxSlots)
                         ELSE Min(CurrentSlots, Floor(maxSlots))
    /\ capacityFresh' = TRUE
    /\ capacityBoot' = boot
    /\ healthyTicks' = 0
    /\ pendingBoardTarget' = NextBoardTarget
    /\ pendingBoardHealthyTicks' = NextBoardHealthyTicks
    /\ pendingWarningEpisode' = NextWarningEpisode
    /\ lastPublishedSample' = sample
    /\ lastPublishBefore' = preSlots
    /\ publicationSucceeded' = TRUE
    /\ stage' = "published"
    /\ UNCHANGED <<maxSlots, boot, boardLimit, boardHealthyTicks, warningEpisode,
                    sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, lastBoardSample, lastBoardBefore,
                    lastBoardWasWarningEpisode, lastBoardFit, lastBoardGrew,
                    jobState, eligibleSeen, reservationValid, startedSafely,
                    activeAtTick, criticalAtTick, pauseRequested, pauseStatus>>

PublishFailure ==
    \* board_governor.py:1090-1096
    /\ AllowPublicationFailure
    /\ stage = "decided"
    /\ publicationSucceeded' = FALSE
    /\ stage' = "done"
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, jobState, eligibleSeen,
                    reservationValid, startedSafely, activeAtTick, criticalAtTick,
                    pauseRequested, pauseStatus>>

RequestCriticalPause ==
    \* board_governor.py:1092-1096; heavy.py:1795-1817; heavy.py:1904-1911
    /\ stage = "published"
    /\ sample = "critical"
    /\ activeAtTick
    /\ ~pauseRequested
    /\ pauseRequested' = TRUE
    /\ pauseStatus' = "requested"
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded, jobState,
                    eligibleSeen, reservationValid, startedSafely, activeAtTick,
                    criticalAtTick>>

SignalAccepted ==
    \* heavy.py:1914-1952
    /\ pauseRequested
    /\ pauseStatus = "requested"
    /\ pauseStatus' = "paused"
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded, jobState,
                    eligibleSeen, reservationValid, startedSafely, activeAtTick,
                    criticalAtTick, pauseRequested>>

SignalDenied ==
    \* heavy.py:1788-1792; heavy.py:1914-1927
    /\ AllowSignalFailure
    /\ pauseRequested
    /\ pauseStatus = "requested"
    /\ pauseStatus' = "signal_failed"
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded, jobState,
                    eligibleSeen, reservationValid, startedSafely, activeAtTick,
                    criticalAtTick, pauseRequested>>

RetrySignal ==
    \* heavy.py:2123-2136
    /\ pauseRequested
    /\ pauseStatus = "signal_failed"
    /\ pauseStatus' = "requested"
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded, jobState,
                    eligibleSeen, reservationValid, startedSafely, activeAtTick,
                    criticalAtTick, pauseRequested>>

PublishBoardLimit ==
    \* board_governor.py:993-1031
    /\ stage = "published"
    /\ (sample # "critical" \/ ~activeAtTick \/ pauseRequested)
    /\ boardLimit' = pendingBoardTarget
    /\ boardHealthyTicks' = pendingBoardHealthyTicks
    /\ warningEpisode' = pendingWarningEpisode
    /\ lastBoardSample' = sample
    /\ lastBoardBefore' = preBoardLimit
    /\ lastBoardWasWarningEpisode' = preWarningEpisode
    /\ lastBoardFit' = boardFit
    /\ lastBoardGrew' = (pendingBoardTarget > preBoardLimit)
    /\ stage' = "done"
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, sample, resourceFit, boardFit, identityOK,
                    taskSlotFree, preSlots, preBoardLimit, preWarningEpisode,
                    pendingTarget, pendingHealthyTicks, pendingBoardTarget,
                    pendingBoardHealthyTicks, pendingWarningEpisode,
                    lastPublishedSample, lastPublishBefore, publicationSucceeded,
                    jobState, eligibleSeen, reservationValid, startedSafely,
                    activeAtTick, criticalAtTick, pauseRequested, pauseStatus>>

AdmitJob ==
    \* heavy.py:1523-1563; heavy.py:534-567
    /\ jobState = "waiting"
    /\ sample \in {"healthy", "noise"}
    /\ capacityFresh
    /\ capacityBoot = boot
    /\ resourceFit > ActiveHeavy
    /\ CurrentSlots > ActiveHeavy
    /\ identityOK
    /\ taskSlotFree
    /\ jobState' = "reserved"
    /\ eligibleSeen' = TRUE
    /\ reservationValid' = TRUE
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded,
                    startedSafely, activeAtTick, criticalAtTick, pauseRequested,
                    pauseStatus>>

ExternalStartSuccess ==
    \* heavy.py:2223-2242
    /\ jobState = "reserved"
    /\ reservationValid
    /\ identityOK
    /\ jobState' = "running"
    /\ startedSafely' = TRUE
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded,
                    eligibleSeen, reservationValid, activeAtTick, criticalAtTick,
                    pauseRequested, pauseStatus>>

ExternalStartFailure ==
    \* heavy.py:2213-2269
    /\ AllowStartFailure
    /\ jobState = "reserved"
    /\ jobState' = "failed"
    /\ startedSafely' = FALSE
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    stage, sample, resourceFit, boardFit, identityOK, taskSlotFree,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded,
                    eligibleSeen, reservationValid, activeAtTick, criticalAtTick,
                    pauseRequested, pauseStatus>>

ControllerRestart ==
    \* board_governor.py:1185-1199; board_governor.py:593-602
    /\ AllowRestarts
    /\ stage \in {"start", "done"}
    /\ stage' = "start"
    /\ sample' = "missing"
    /\ resourceFit' = 0
    /\ boardFit' = FALSE
    /\ identityOK' = FALSE
    /\ taskSlotFree' = FALSE
    /\ activeAtTick' = FALSE
    /\ criticalAtTick' = FALSE
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, capacityFresh, publishedSlots,
                    healthyTicks, boardLimit, boardHealthyTicks, warningEpisode,
                    preSlots, preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded, jobState,
                    eligibleSeen, reservationValid, startedSafely, pauseRequested,
                    pauseStatus>>

HostReboot ==
    \* board_governor.py:572-602; heavy.py:534-549
    /\ AllowRestarts
    /\ jobState \in {"waiting", "failed"}
    /\ stage \in {"start", "done"}
    /\ boot' = 1 - boot
    /\ stage' = "start"
    /\ sample' = "missing"
    /\ resourceFit' = 0
    /\ boardFit' = FALSE
    /\ identityOK' = FALSE
    /\ taskSlotFree' = FALSE
    /\ healthyTicks' = 0
    /\ boardHealthyTicks' = 0
    /\ warningEpisode' = FALSE
    /\ activeAtTick' = FALSE
    /\ criticalAtTick' = FALSE
    /\ UNCHANGED <<maxSlots, capacityBoot, capacityFresh, publishedSlots,
                    boardLimit, preSlots, preBoardLimit, preWarningEpisode,
                    pendingTarget, pendingHealthyTicks, pendingBoardTarget,
                    pendingBoardHealthyTicks, pendingWarningEpisode,
                    lastPublishedSample, lastBoardSample, lastPublishBefore,
                    lastBoardBefore, lastBoardWasWarningEpisode, lastBoardFit,
                    lastBoardGrew, publicationSucceeded, jobState, eligibleSeen,
                    reservationValid, startedSafely, pauseRequested, pauseStatus>>

ExpireCapacity ==
    \* board_governor.py:572-590; heavy.py:534-549
    /\ Environment = "adversarial"
    /\ capacityFresh
    /\ capacityFresh' = FALSE
    /\ UNCHANGED <<maxSlots, boot, capacityBoot, publishedSlots, healthyTicks,
                    boardLimit, boardHealthyTicks, warningEpisode, stage, sample,
                    resourceFit, boardFit, identityOK, taskSlotFree, preSlots,
                    preBoardLimit, preWarningEpisode, pendingTarget,
                    pendingHealthyTicks, pendingBoardTarget, pendingBoardHealthyTicks,
                    pendingWarningEpisode, lastPublishedSample, lastBoardSample,
                    lastPublishBefore, lastBoardBefore, lastBoardWasWarningEpisode,
                    lastBoardFit, lastBoardGrew, publicationSucceeded, jobState,
                    eligibleSeen, reservationValid, startedSafely, activeAtTick,
                    criticalAtTick, pauseRequested, pauseStatus>>

Next == CaptureReading \/ DecideTargets \/ CensusFailure \/ PublishCapacity
        \/ PublishFailure
        \/ RequestCriticalPause \/ SignalAccepted \/ SignalDenied \/ RetrySignal
        \/ PublishBoardLimit \/ AdmitJob \/ ExternalStartSuccess
        \/ ExternalStartFailure \/ ControllerRestart \/ HostReboot \/ ExpireCapacity

FairSteps ==
    /\ WF_vars(CaptureReading)
    /\ WF_vars(DecideTargets)
    /\ WF_vars(PublishCapacity)
    /\ WF_vars(RequestCriticalPause)
    /\ WF_vars(PublishBoardLimit)
    /\ SF_vars(AdmitJob)
    /\ WF_vars(ExternalStartSuccess)

Spec == Init /\ [][Next]_vars /\ FairSteps

TypeOK ==
    /\ maxSlots \in MaxSlots
    /\ boot \in {0, 1}
    /\ capacityBoot \in {0, 1}
    /\ capacityFresh \in BOOLEAN
    /\ publishedSlots \in 0..4
    /\ healthyTicks \in 0..Window
    /\ boardLimit \in 0..4
    /\ boardHealthyTicks \in 0..Window
    /\ warningEpisode \in BOOLEAN
    /\ stage \in Stages
    /\ sample \in Signals
    /\ resourceFit \in 0..4
    /\ boardFit \in BOOLEAN
    /\ identityOK \in BOOLEAN
    /\ taskSlotFree \in BOOLEAN
    /\ preSlots \in 0..4
    /\ preBoardLimit \in 0..4
    /\ preWarningEpisode \in BOOLEAN
    /\ pendingTarget \in 0..4
    /\ pendingHealthyTicks \in 0..Window
    /\ pendingBoardTarget \in 0..4
    /\ pendingBoardHealthyTicks \in 0..Window
    /\ pendingWarningEpisode \in BOOLEAN
    /\ lastPublishedSample \in Signals
    /\ lastBoardSample \in Signals
    /\ lastPublishBefore \in 0..4
    /\ lastBoardBefore \in 0..4
    /\ lastBoardWasWarningEpisode \in BOOLEAN
    /\ lastBoardFit \in BOOLEAN
    /\ lastBoardGrew \in BOOLEAN
    /\ publicationSucceeded \in BOOLEAN
    /\ jobState \in Jobs
    /\ eligibleSeen \in BOOLEAN
    /\ reservationValid \in BOOLEAN
    /\ startedSafely \in BOOLEAN
    /\ activeAtTick \in BOOLEAN
    /\ criticalAtTick \in BOOLEAN
    /\ pauseRequested \in BOOLEAN
    /\ pauseStatus \in PauseStates

NoAboveCeiling == publishedSlots <= maxSlots

DecidedGrowthStep ==
    (stage = "decided" /\ pendingTarget > Max(Floor(maxSlots), preSlots))
      => (pendingTarget = preSlots + 1 /\ sample = "healthy"
          /\ healthyTicks = Window /\ resourceFit >= preSlots + 1)

NoRaiseOnBadReading ==
    (publicationSucceeded /\ lastPublishedSample \in BadSignals)
      => publishedSlots <= lastPublishBefore

FloorAfterFreshNoncritical ==
    (publicationSucceeded /\ capacityFresh /\ capacityBoot = boot
       /\ lastPublishedSample \in GoodSignals)
    => publishedSlots >= Floor(maxSlots)

CriticalTickComplete ==
    (stage = "done" /\ criticalAtTick)
    => (publishedSlots = 0 /\ (~activeAtTick \/ pauseRequested))

SafeReservation == jobState = "reserved" => reservationValid
SafeStartedJob == jobState = "running" => startedSafely

BoardOneSpare == boardLimit <= BoardSnapshotActive + 1
BoardNoRaiseOnBadReading ==
    lastBoardSample \in BadSignals => boardLimit <= lastBoardBefore
BoardCriticalZero == lastBoardSample = "critical" => boardLimit = 0
BoardGrowthOneStep ==
    lastBoardGrew => boardLimit = lastBoardBefore + 1 /\ lastBoardFit
                   /\ lastBoardBefore <= BoardSnapshotActive
BoardWarningHalvesOnce ==
    lastBoardSample = "warning"
    => boardLimit = IF lastBoardWasWarningEpisode
                    THEN Min(lastBoardBefore, BoardSnapshotActive)
                    ELSE Min(lastBoardBefore \div 2, BoardSnapshotActive)

NoncriticalTickFloor ==
    (stage = "done" /\ lastPublishedSample # "critical")
    => publishedSlots >= Floor(maxSlots)

NoFailedStart == jobState # "failed"

Safety == /\ TypeOK
    /\ NoAboveCeiling
    /\ DecidedGrowthStep
    /\ NoRaiseOnBadReading
    /\ FloorAfterFreshNoncritical
    /\ CriticalTickComplete
    /\ SafeReservation
    /\ SafeStartedJob
    /\ BoardOneSpare
    /\ BoardNoRaiseOnBadReading
    /\ BoardCriticalZero
    /\ BoardGrowthOneStep
    /\ BoardWarningHalvesOnce

CriticalRequestWithinTick ==
    []((stage = "done" /\ criticalAtTick /\ activeAtTick)
       => pauseRequested)

EligibleQueueStarts == [] (eligibleSeen => <> (jobState = "running"))

QueueStarts == [] (jobState = "waiting" => <> (jobState = "running"))

StrictNoCriticalQueueStarts ==
    []((Environment = "missing") => <> (jobState = "running"))

HealthyWindowRaises ==
    []((stage = "sampled" /\ EligibleSample /\ healthyTicks = Window
        /\ CurrentSlots >= Floor(maxSlots) /\ CurrentSlots < maxSlots
        /\ resourceFit >= CurrentSlots + 1)
       => <> (publishedSlots >= preSlots + 1))

=============================================================================
