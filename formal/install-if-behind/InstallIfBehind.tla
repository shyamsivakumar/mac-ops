------------------------- MODULE InstallIfBehind -------------------------
\* One run of run_install_if_behind at a time (flock via install_lock,
\* install_if_behind.py:759). Each action is one step of the run, a push to
\* origin/main, or a process kill.
EXTENDS Integers, FiniteSets

\* ModelFix TRUE: a persisted pending-observation marker is written with the
\* receipt and read first by the next run. The code has no such marker.
\* StartEmpty TRUE: no receipt exists at the start (not_installed).
CONSTANTS ModelFix, StartEmpty, MaxCrashes, MaxOrigin

VARIABLES
  origin,    \* origin/main commit
  receipt,   \* installed source_commit, -1 (None) if no receipt
  active,    \* release the controller runs
  verified,  \* commits whose observation passed, plus the initial commit
  pc,        \* "idle" | "locked" | "decided" | "installing" | "observing" | "rollingBack"
  prev,      \* status_before["receipt"] (line 813) or the marker's copy
  target,    \* target_commit of this run
  lock,
  crashes,
  note,      \* "ok" | "crashed" | "errored", how the last run ended
  rolled,    \* the last run rolled back to prev
  pend,      \* marker: an install has not been observed yet
  pendPrev

vars == <<origin, receipt, active, verified, pc, prev, target, lock, crashes, note, rolled, pend, pendPrev>>

None == -1
Commits == 0..MaxOrigin

Init ==
  /\ origin = 0
  /\ receipt = IF StartEmpty THEN None ELSE 0
  /\ active = receipt
  /\ verified = IF StartEmpty THEN {} ELSE {0}
  /\ pc = "idle"
  /\ prev = None
  /\ target = 0
  /\ lock = FALSE
  /\ crashes = 0
  /\ note = "ok"
  /\ rolled = FALSE
  /\ pend = FALSE
  /\ pendPrev = None

Push ==
  /\ origin < MaxOrigin
  /\ origin' = origin + 1
  /\ UNCHANGED <<receipt, active, verified, pc, prev, target, lock, crashes, note, rolled, pend, pendPrev>>

\* install_lock acquired, then status_before read. Lines 759, 813.
Start ==
  /\ pc = "idle"
  /\ ~lock
  /\ lock' = TRUE
  /\ pc' = "locked"
  /\ prev' = receipt
  /\ note' = "ok"
  /\ rolled' = FALSE
  /\ UNCHANGED <<origin, receipt, active, verified, target, crashes, pend, pendPrev>>

\* fetch, classify_commits, check_gate, evaluate_decision. Lines 813-850.
Decide ==
  /\ pc = "locked"
  /\ \/ /\ ModelFix /\ pend
        /\ pc' = "observing"
        /\ prev' = pendPrev
        /\ target' = active
        /\ UNCHANGED lock
     \/ /\ ~(ModelFix /\ pend)
        /\ receipt = origin
        /\ pc' = "idle"
        /\ lock' = FALSE
        /\ UNCHANGED <<prev, target>>
     \/ /\ ~(ModelFix /\ pend)
        /\ receipt # origin
        /\ pc' = "idle"
        /\ lock' = FALSE
        /\ UNCHANGED <<prev, target>>
     \/ /\ ~(ModelFix /\ pend)
        /\ receipt # origin
        /\ pc' = "installing"
        /\ target' = origin
        /\ UNCHANGED <<prev, lock>>
  /\ UNCHANGED <<origin, receipt, active, verified, crashes, note, rolled, pend, pendPrev>>

\* install.sh writes the receipt and activates the release. Lines 965-968.
Install ==
  /\ pc = "installing"
  /\ receipt' = target
  /\ active' = target
  /\ pend' = ModelFix
  /\ pendPrev' = prev
  /\ pc' = "observing"
  /\ UNCHANGED <<origin, verified, prev, target, lock, crashes, note, rolled>>

\* observe_controller returns passed. Lines 974-980, 1041-1053.
ObservePass ==
  /\ pc = "observing"
  /\ verified' = verified \cup {target}
  /\ pend' = FALSE
  /\ pc' = "idle"
  /\ lock' = FALSE
  /\ UNCHANGED <<origin, receipt, active, prev, target, crashes, note, rolled, pendPrev>>

\* Observation failed or the install raised. Lines 981-1000.
ObserveFail ==
  /\ pc = "observing"
  /\ pc' = "rollingBack"
  /\ UNCHANGED <<origin, receipt, active, verified, prev, target, lock, crashes, note, rolled, pend, pendPrev>>

\* rollback_to_release when a previous receipt exists, else a reported
\* error with the new release still active. Lines 1003-1039, 605-625.
Rollback ==
  /\ pc = "rollingBack"
  /\ pc' = "idle"
  /\ lock' = FALSE
  /\ IF prev # None
     THEN /\ receipt' = prev /\ active' = prev
          /\ rolled' = TRUE /\ note' = note /\ pend' = FALSE
     ELSE /\ UNCHANGED <<receipt, active, rolled, pend>>
          /\ note' = "errored"
  /\ UNCHANGED <<origin, verified, prev, target, crashes, pendPrev>>

\* SIGTERM or SIGKILL. The except tuple at 981-987 does not catch
\* KeyboardInterrupt or SystemExit, so no rollback runs. The flock is released.
Crash ==
  /\ pc # "idle"
  /\ crashes < MaxCrashes
  /\ crashes' = crashes + 1
  /\ pc' = "idle"
  /\ lock' = FALSE
  /\ note' = "crashed"
  /\ UNCHANGED <<origin, receipt, active, verified, prev, target, rolled, pend, pendPrev>>

Run == Start \/ Decide \/ Install \/ ObservePass \/ ObserveFail \/ Rollback

Next == Run \/ Push \/ Crash

Spec == Init /\ [][Next]_vars
LiveSpec == Init /\ [][Next]_vars /\ WF_vars(Run)

TypeOK ==
  /\ origin \in Commits /\ target \in Commits
  /\ receipt \in Commits \cup {None} /\ active \in Commits \cup {None}
  /\ prev \in Commits \cup {None} /\ pendPrev \in Commits \cup {None}
  /\ verified \subseteq Commits
  /\ pc \in {"idle", "locked", "installing", "observing", "rollingBack"}
  /\ lock \in BOOLEAN /\ rolled \in BOOLEAN /\ pend \in BOOLEAN
  /\ crashes \in 0..MaxCrashes
  /\ note \in {"ok", "crashed", "errored"}

NoDoubleInstall == pc \in {"installing", "observing"} => lock

\* An idle system with no crash or reported error pending runs only
\* observed releases.
StableMeansVerified ==
  (pc = "idle" /\ note = "ok") => (active = None \/ active \in verified)

RollbackRestoresPrev == rolled => (receipt = prev /\ active = prev)

EventuallyIdle == []<>(pc = "idle")
=========================================================================
