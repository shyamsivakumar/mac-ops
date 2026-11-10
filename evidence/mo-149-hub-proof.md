# MO-149 hub startup and concurrency

Refs MO-149. Frozen base: `debbe637b07cbae40daadf244089ef539ccc7094` (MO-147 and MO-148 merged).

## Reproduction and implementation

Before source edits, `python3 verification/check_hub_single_instance.py` failed (4 failures, 1 error; 3 tests). Arguments were ignored; module-level store loading preceded usage handling; a second process remained running instead of rejecting ownership and unconditionally replaced the socket. All processes used a disposable HOME and its real `.empryo-hub/hub.sock` path, never the installed binary.

The source now checks arguments first and takes a nonblocking fcntl flock on a persistent `hub.lock` inode before store reads/socket mutation. The process-lifetime descriptor is close-on-exec. Losing starters exit 1 with `already running`; arguments exit 0 with usage. Provider slot state, routing reads, wait/release paths and status limits were removed; `turnLimits` and circuit breakers remain.

## Approved existing-proof migration

Initial review failed for obsolete base-proof loader/provider-slot assumptions and then-pending wall-clock evidence. Exact reviewer findings and the user's quoted authorization are preserved in `evidence/mo-149-followup.md`; the original review is `evidence/mo-149-review.md`.

Only the approved canonical-proof loader, release instrumentation, and provider-queue cases changed. Five unaffected methods are byte-identical to base. The replacement checks two same-provider turns really run together, independently expire and release engines exactly once, resumed clocks reset, old grace timers cannot kill newer turns, and drain queueing never consumes budget. Configuration checks assert no provider limits and unchanged turnLimits. The original run-count, record-count, cancellation, and persisted full-record checks remain where applicable. The interim separate uncapped runner was folded into this canonical proof and removed.

## Verification

Current full output: `evidence/mo-149-followup-proof.log`.

- `python3 verification/check_hub_single_instance.py`: **5 tests OK**. Lock rejection preserves store bytes/mtimes and socket inode, first PID still serves, malformed stores are not read by a losing starter, argument handling touches no hub state, and lock release permits a replacement on the stale socket.
- `python3 verification/check_hub_turn_budget.py`: **7 tests OK**. Concurrent providers, drain clocks, resume/grace fencing, permission deferral, default/legacy/override validation, extended tools, persisted drain/reload override, and normal/fallback merge-review provenance.
- `python3 -m unittest discover -s tests -v`: **51 tests OK**.
- `python3 -m py_compile empryo/bin/emp-hub verification/check_hub_single_instance.py verification/check_hub_turn_budget.py`: exit 0.
- `git diff --check`: clean.
- Previous real 601-second wall-clock run: **PASS**, two concurrent real sleep children, zero clock offset, both turns expired with one cancellation/engine release each and failed records persisted. Full output: `evidence/mo-149-wall-clock.log`.
- Fresh canonical `python3 -u verification/check_hub_turn_budget.py --wall-clock`: **PASS, exit 0 after 10m 1s**. Its `SECOND HUB` banner and final PASS line are in `evidence/mo-149-canonical-wall-clock.log`; both real concurrent turns expired once, released engines once and persisted full failed run records.

Historical reproduction, obsolete-proof failures, and interim proof output are retained in `evidence/mo-149-hub-proof.log`. A fixture-only failure from macOS Python's bytecode cache writing into fresh HOME was resolved with `PYTHONDONTWRITEBYTECODE=1`; the no-HOME-creation assertion was not weakened.

## Final review

Third Opus review: **VERDICT: PASS**; no critical/major findings. Full read-only report: `evidence/mo-149-review-final.md` (not independently rerun). The remaining minor request for explicit canonical wall-clock command/exit/duration metadata was addressed before publishing. Exact original blockers, approval and resolutions: `evidence/mo-149-followup.md`.

## Deployment hold

No install, production drain, restart, cancellation, provider call or installed-binary invocation. The old hub has no lock: do not start the new version alongside it. Push and PR are requested, not deployment. After the separate Opus gate and coordinator go, perform `./install.sh empryo` and exactly one coordinated drain/restart. Rollback: reinstall the previous emp-hub.
