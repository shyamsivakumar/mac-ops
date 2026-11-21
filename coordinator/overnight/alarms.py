#!/usr/bin/env python3
"""The mute for the alarms the shift raises on the coordinator's board.

An alarm is a board item with an id and a cause. The id names the alarm
and the cause says what is wrong: the failing exit code, the silent log,
the board that stopped moving. The two together are the alarm's key.

Once the alarm has been answered on the decisions board, or the
coordinator has routed it, the key stays quiet for four hours: the next
tick writes no board item for that key and raises no alert for it. A
different cause is a different key, and it alarms at once. A muted alarm
still logs one line per tick, so the shift's log says what it did not
raise.

The mute state lives in the shift's own records, under
`run/mute-state.json` next to the stall state, and not in the board file:
the coordinator rewrites the board file, and a board file that is
rewritten must not take the mute with it.

One thing mutes a key: an explicit acknowledgement. It is a record with
the time it was given and the time the mute ends, and it is written when
the alarm was answered on the decisions board or when the coordinator
recorded it as routed. The coordinator panel writes it when Shyam answers
(the `alarms ack <alarm-id>` command), and the command is there for the
coordinator and for a person.

The record is the whole rule. A board item that went missing is not an
acknowledgement: the board has more than one writer and one of them can
lose the item for a tick, so an alarm nobody answered is never silenced.
An alarm that is not true any more drops its "raised" mark, so the same
cause can alarm again the next time it is true, but an acknowledgement
that is still running keeps the key quiet.

Two writers write the state: the tick and the panel. They take the lock
beside the state for the whole read, merge and replace, and a writer that
cannot take the lock fails its write. A lock that is not held is not a
lock: a write that goes on without one can replace the file under a
concurrent acknowledgement and take that acknowledgement with it.
"""

import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import sys
from pathlib import Path

for _dir in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent / "bin"):
    if (_dir / "journal.py").is_file() and str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import journal

# How long a key stays quiet after it was answered or routed.
MUTE_SECONDS = 4 * 60 * 60
DECISIONS_PATH = os.environ.get("COORDINATOR_DECISIONS", "/Users/shyamsivakumar/Code/coordinator/decisions.json")
# The key of the mute state inside the state file.
STATE_KEY = "alarms"
# The minutes of a quiet log and the minutes of a stuck run change on
# every tick, so they are not part of the cause. The idle tick count of a
# stall is the same: a stall that is reported on the fourth tick is the
# same stall as the one reported on the third.
VOLATILE = re.compile(r"\d+ min \(limit \d+\)|running \d+ min")
# The idle tick count of a stall changes with the tick it is reported on.
VOLATILE_TICKS = re.compile(r"\d+ ticks")
# The shift's own records: the mute state lives beside the stall state.
# The path follows the shift's root, so the command the coordinator runs
# and the shift that reads the state write the same file.
MUTE_PATH = os.environ.get("OVERNIGHT_MUTE_STATE")


def default_mute_path():
    """Return the path of the mute state in the shift's own folder.

    The folder is the shift's root, which the installer creates and
    which `OVERNIGHT_ROOT` or `MAC_OPS_COORDINATOR_DIR` can move."""
    root = os.environ.get("OVERNIGHT_ROOT")
    if root:
        return Path(root).expanduser() / "run" / "mute-state.json"
    coordinator = os.environ.get("MAC_OPS_COORDINATOR_DIR")
    if coordinator:
        return Path(coordinator).expanduser() / ".overnight" / "run" / "mute-state.json"
    return Path.home() / "Code" / "coordinator" / ".overnight" / "run" / "mute-state.json"


MUTE_PATH = MUTE_PATH or str(default_mute_path())


def stamp(now=None):
    """Return the UTC stamp of a moment."""
    moment = now or dt.datetime.now(dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def moment(text):
    """Return the epoch second of a stamp, or None when it is not one."""
    if not isinstance(text, str) or not text:
        return None
    try:
        parsed = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc).timestamp()


def cause_of(text):
    """Return the cause of one alarm, without the parts that change.

    The minutes of a quiet log and the minutes of a stuck run change on
    every tick, so they are not part of the cause: the same quiet log is
    the same cause. The exit code and the signal are part of it: a job
    that fails with a new code is a new cause and alarms at once."""
    cause = VOLATILE.sub("<time>", str(text or "")).strip()
    return VOLATILE_TICKS.sub("<ticks>", cause)


def key_of(alarm_id, cause):
    """Return the key of one alarm: its id and its cause."""
    return f"{alarm_id}|{cause_of(cause)}"


def state_path():
    """Return the path of the file that holds the mute state."""
    return Path(MUTE_PATH)


def load_state():
    """Return the mute state the shift keeps.

    A state file that is not there is an empty state: every alarm is
    measured again from this tick on. A state file that cannot be read
    is not an empty state: reading it as empty would let the next alarm
    overwrite every acknowledgement it holds, and the alarms that were
    answered would come back before their four hours are over. The read
    failure is raised, and the caller publishes the alarm as unchecked
    without writing over the state it could not read.

    A file that holds text that is not JSON is a file that cannot be
    read, in the same way: the acknowledgements it still holds are
    recoverable and must not be lost, so the failure is raised, the
    alarm is published as unchecked, and the file is left as it is."""
    try:
        text = state_path().read_text()
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text)
    except ValueError as error:
        # A damaged file is not an empty state: reading it as empty would
        # let the next alarm overwrite it with its own key, and the
        # acknowledgements the file still holds would be lost. The file
        # is kept as it is, and the alarm is published as unchecked.
        raise ValueError(f"the mute state is not readable: {error}") from error
    state = data.get(STATE_KEY) if isinstance(data, dict) else None
    return state if isinstance(state, dict) else {}


def acked_at(record):
    """Return the epoch second of a record's acknowledgement, or 0."""
    return moment(record.get("acked")) or 0


def merge(current, state):
    """Return the two states merged, and the newer acknowledgement wins.

    A tick reads the state, the panel records an acknowledgement and
    writes the file, and the tick writes its older snapshot. The
    acknowledgement is newer, so it wins: the tick must not take it with
    it. A record with no acknowledgement and no raised mark says nothing
    and is dropped, so the state stays bounded."""
    merged = {}
    for key in set(current) | set(state):
        mine = state.get(key) if isinstance(state.get(key), dict) else {}
        theirs = current.get(key) if isinstance(current.get(key), dict) else {}
        if not mine:
            record = dict(theirs)
        elif not theirs:
            record = dict(mine)
        else:
            record = dict(mine)
            if acked_at(theirs) > acked_at(mine):
                record["acked"] = theirs.get("acked")
                record["until"] = theirs.get("until")
        if not record.get("acked") and not record.get("raised"):
            continue
        merged[key] = record
    return merged


def take_lock(path=None):
    """Take a lock file and return the open handle, or None.

    A lock that cannot be taken is not a lock. A writer that cannot take
    it must fail its write, not write the file unlocked and take a
    concurrent acknowledgement with it. The handle is let go with
    `drop_lock`."""
    path = Path(path or (str(MUTE_PATH) + ".lock"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(descriptor, "r+")
    except OSError:
        return None
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
    except OSError:
        try:
            handle.close()
        except OSError:
            pass
        return None
    return handle


def drop_lock(handle):
    """Let go of the state lock."""
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        handle.close()
    except OSError:
        pass


def board_update(target, alarm_id, action, item=None, attempts=5, create=False):
    """Write one alarm onto the board, serialized or by compare-and-swap.

    The board lock is taken first, and the board is read, changed and
    replaced while it is held. A board lock that cannot be taken does not
    suppress the alarm: the write falls back to a compare-and-swap, which
    re-reads the board and only replaces it when nobody else wrote in
    between, so two publishers still cannot erase one another's alarm.
    A publication that cannot be made safe after a few tries says so.

    `action` is "raise" to put the item on the board and "remove" to take
    it off. `create` makes a missing board under the lock, so two first
    publishers cannot overwrite one another. Return "wrote" or "failed"."""
    path = Path(target)
    handle = take_lock(str(path) + ".lock")
    try:
        if handle is not None:
            return "wrote" if write_alarm(path, alarm_id, action, item, create) else "failed"
    finally:
        if handle is not None:
            drop_lock(handle)
    # The board lock could not be taken. The alarm is still published: a
    # publisher that stops here would hide a real failure from Shyam for
    # as long as the lock file cannot be opened.
    for _ in range(attempts):
        result = swap_alarm(path, alarm_id, action, item)
        if result != "retry":
            return result
    return "failed"


OWNER_IDS = re.compile(
    r"factory-zero-merge|factory-overnight-stall"
    r"|lane-gate-rounds-shyamsivakumar-mac-ops-\d+|.+-MO-\d+")


def board_for(decisions, alarm_id):
    """The board file an item id belongs to.

    The mac-ops tooling alarms go to the mac-ops owner's board, which sits
    beside the decisions board unless COORDINATOR_OWNER_BOARD moves it.
    Every other id stays on the decisions board."""
    if not OWNER_IDS.fullmatch(str(alarm_id)):
        return Path(decisions)
    return Path(os.environ.get("COORDINATOR_OWNER_BOARD")
                or Path(decisions).with_name("mac-ops-owner.json"))


def route_update(decisions, alarm_id, action, item=None):
    """board_update on the board the id belongs to, clearing any stale copy.

    An owner item is raised or removed on the owner board, and the same id
    is taken off the decisions board when it is still there. Return
    "wrote" or "failed"."""
    target = board_for(decisions, alarm_id)
    if target == Path(decisions):
        return board_update(decisions, alarm_id, action, item)
    if board_update(target, alarm_id, action, item, create=True) != "wrote":
        return "failed"
    return clear_stale(decisions, alarm_id)


def clear_stale(decisions, alarm_id, attempts=5):
    """Take an id off the decisions board when it is still there.

    The board is replaced only when its bytes still match the read, under
    the board lock, because the watchdog writes the same file without the
    lock. A lock that cannot be taken, or a board that keeps changing,
    returns "failed" for the next tick."""
    path = Path(decisions)
    handle = take_lock(str(path) + ".lock")
    if handle is None:
        return "failed"
    try:
        for _ in range(attempts):
            _, board = read_board(path)
            if board is None or not any(
                    isinstance(e, dict) and e.get("id") == alarm_id for e in board["items"]):
                return "wrote"
            result = swap_alarm(path, alarm_id, "remove", None)
            if result != "retry":
                return result
        return "failed"
    finally:
        drop_lock(handle)


def migrate_stale(decisions, alarm_id):
    """Move an owner item still on the decisions board to the owner board.

    The card is moved as it is, so a card Shyam answered is not raised
    again. Return "wrote" or "failed"."""
    _, board = read_board(Path(decisions))
    held = [e for e in (board or {"items": []})["items"]
            if isinstance(e, dict) and e.get("id") == alarm_id]
    if not held or board_for(decisions, alarm_id) == Path(decisions):
        return "wrote"
    return route_update(decisions, alarm_id, "raise", held[0])


def read_board(path):
    """Return (the board's bytes, the board) or (bytes, None)."""
    try:
        before = path.read_bytes()
    except FileNotFoundError:
        return b"", None
    try:
        board = json.loads(before)
    except ValueError:
        return before, None
    if not isinstance(board, dict) or not isinstance(board.get("items"), list):
        return before, None
    return before, board


def change_board(board, alarm_id, action, item):
    """Return the board with the one alarm set, and True when it changed."""
    kept = [
        entry
        for entry in board["items"]
        if not (isinstance(entry, dict) and entry.get("id") == alarm_id)
    ]
    if action == "raise" and item is not None:
        kept.append(item)
    changed = kept != board["items"]
    board["items"] = kept
    board["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return board, changed


def alarm_shape(entry):
    if entry is None:
        return None
    return entry.get("group"), cause_of(entry.get("cause") or entry.get("title"))


def alarm_event(board, alarm_id, action, item):
    held = next((e for e in board["items"]
                 if isinstance(e, dict) and e.get("id") == alarm_id), None)
    if action == "raise" and item is not None:
        return ("alarm_raised", item.get("group")) if alarm_shape(held) != alarm_shape(item) else None
    return ("alarm_withdrawn", held.get("group")) if held is not None else None


def journal_alarm(path, alarm_id, event):
    if event is not None:
        journal.emit(event[0], "alarms", alarm=alarm_id, board=str(path), group=event[1])


def write_alarm(path, alarm_id, action, item, create=False):
    """Read, change and replace the board under the caller's lock."""
    _, board = read_board(path)
    if board is None and create and not path.exists():
        if action != "raise":
            return True
        board = {"items": []}
    if board is None:
        return False
    event = alarm_event(board, alarm_id, action, item)
    board, _ = change_board(board, alarm_id, action, item)
    if not write_board(path, board):
        return False
    journal_alarm(path, alarm_id, event)
    return True


def swap_alarm(path, alarm_id, action, item):
    """Publish one alarm by compare-and-swap.

    The board is read, changed, and replaced only when nobody wrote it
    since the read. The result is read back, so a write that another
    publisher replaced is not counted as delivered. Return "wrote",
    "retry" or "failed"."""
    before, board = read_board(path)
    if board is None:
        return "failed"
    event = alarm_event(board, alarm_id, action, item)
    board, _ = change_board(board, alarm_id, action, item)
    try:
        if path.read_bytes() != before:
            # Another publisher wrote the board since the read, so this
            # write would erase its alarm. Try again on the new board.
            return "retry"
        if not write_board(path, board):
            return "failed"
        _, after = read_board(path)
        if after is None:
            return "failed"
        present = [
            entry for entry in after["items"]
            if isinstance(entry, dict) and entry.get("id") == alarm_id
        ]
        if action == "raise" and not present:
            return "retry"
        journal_alarm(path, alarm_id, event)
        return "wrote"
    except OSError:
        return "failed"


def write_board(path, board):
    """Replace the board from a temporary file of this writer's own."""
    temporary = Path(f"{path}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(board, indent=1))
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        return False
    return True


@contextlib.contextmanager
def board_locked(path):
    """Hold the board lock while the board is read, changed and replaced.

    The board lock is its own file, beside the board, and not the mute
    lock: a mute storage that cannot be locked must not leave the board
    unprotected, or two publishers read the same board and one alarm
    disappears. The lock is held across the read, the update and the
    replace, so the board a publisher writes is the board it read.

    It yields True when the lock could not be taken: the publisher then
    does not write the board, because two publishers writing the same
    board would erase one another's alarm, and says so out loud."""
    handle = take_lock(str(path) + ".lock")
    try:
        yield handle is None
    finally:
        if handle is not None:
            drop_lock(handle)


@contextlib.contextmanager
def locked():
    """Hold the state lock while the state is read and written.

    Two writers of the same file must not read, merge and replace it at
    the same time: the tick and the panel both write it, and a write that
    lands between the read and the replace of the other writer is lost.
    The lock is held across the whole read, merge and replace."""
    handle = take_lock()
    if handle is None:
        raise OSError("the mute state lock could not be taken")
    try:
        yield
    finally:
        drop_lock(handle)


def write_state(state):
    """Write the mute state and return True when it went to the file.

    The write is atomic, so a tick that reads while the state is being
    written reads the old state or the new one, never half of one. The
    temporary file carries the writer's own name, so two writers never
    share one."""
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f"{path.name}.{os.getpid()}.tmp"
        temporary.write_text(json.dumps({STATE_KEY: state}, indent=1) + "\n")
        os.replace(temporary, path)
    except OSError:
        return False
    return True


def save_state(state):
    """Write the mute state and return True when it went to the file.

    The file is read again under the lock and merged, so an
    acknowledgement that landed while the tick was running is kept, and
    no other writer can land one between that read and the replace."""
    try:
        with locked():
            return write_state(merge(load_state(), state))
    except (OSError, ValueError):
        return False


def entry(state, key):
    """Return the record of one key, or an empty record."""
    value = state.get(key) if isinstance(state, dict) else None
    return value if isinstance(value, dict) else {}


def until(state, key):
    """Return the epoch second the key stays quiet until, or None."""
    return moment(entry(state, key).get("until"))


def muted(state, key, now=None):
    """Return True when the key is quiet right now."""
    stop = until(state, key)
    if stop is None:
        return False
    current = now or dt.datetime.now(dt.timezone.utc)
    return current.timestamp() < stop


def acknowledge(state, key, now=None):
    """Quiet one key for four hours and return the record it wrote.

    The acknowledgement is the answer: the key stays quiet until the four
    hours are over, and a different cause is a different key."""
    current = now or dt.datetime.now(dt.timezone.utc)
    record = dict(entry(state, key))
    record["acked"] = stamp(current)
    record["until"] = stamp(current + dt.timedelta(seconds=MUTE_SECONDS))
    state[key] = record
    return record


def raised(state, alarm_id, cause, now=None):
    """Record that the key is on the board and return the record it wrote.

    A raised key has no acknowledgement: the alarm is on the board and
    waits for an answer."""
    current = now or dt.datetime.now(dt.timezone.utc)
    key = key_of(alarm_id, cause)
    state[key] = {"cause": cause_of(cause), "raised": stamp(current)}
    return state[key]


def gone(state, alarm_id):
    """Mark every key of one alarm as not true any more.

    The key keeps its acknowledgement, so an alarm that was answered
    stays quiet for the rest of the four hours, but the "raised" mark
    goes, so the same cause can alarm again when it is true again."""
    prefix = f"{alarm_id}|"
    for key in list(state or {}):
        if not key.startswith(prefix):
            continue
        record = state[key]
        if not isinstance(record, dict):
            continue
        record.pop("raised", None)


def decide(state, alarm_id, cause, now=None):
    """Return what the shift does with one alarm: "raise" or "quiet".

    The rule: a key with an acknowledgement stays quiet for four hours,
    and every other key is raised at once. Nothing else quiets an alarm.
    A board item that went missing is not an acknowledgement, so an alarm
    that nobody answered is never silenced."""
    current = now or dt.datetime.now(dt.timezone.utc)
    key = key_of(alarm_id, cause)
    record = entry(state, key)
    if record.get("acked"):
        stop = moment(record.get("until"))
        if stop is not None and current.timestamp() < stop:
            return "quiet"
        # The four hours are over, so the alarm is raised again.
    return "raise"


USAGE = """usage: alarms ack <alarm-id> <cause>   quiet that cause of that alarm for four hours
       alarms status                       show the alarm keys and until when they are quiet
"""


def decide_and_publish(alarm_id, cause, publish):
    """Decide what to do with one alarm and publish it, under the lock.

    The decision is taken from the state the lock protects, the state is
    written, and the alarm is published, all while the lock is held. An
    acknowledgement that lands while the caller works cannot slip between
    the decision and the publication: the caller publishes exactly what
    this decision says, and an acknowledgement that comes after it
    applies from the next tick.

    `publish` is called once, with the decision, while the lock is
    held. It returns "failed" when it could not write the board, and the
    decision is returned otherwise. A lock that cannot be taken, or a
    state that cannot be written, publishes the alarm as "unchecked":
    the alarm cannot be quiet, and a storage failure must not hide a real
    failure from Shyam."""
    handle = take_lock()
    if handle is None:
        # The state cannot be locked, so the alarm cannot be quiet. It is
        # published anyway, and the fault is said out loud.
        return publish("unchecked") or "unchecked"
    try:
        try:
            state = load_state()
            action = decide(state, alarm_id, cause)
            if action == "raise":
                raised(state, alarm_id, cause)
                if not write_state(merge(load_state(), state)):
                    # The key could not be written, so the answer to this
                    # alarm cannot be recorded. The alarm is published
                    # anyway: a storage failure must not hide a real
                    # failure.
                    action = "unchecked"
            # A quiet tick changes nothing, so it writes nothing: a write
            # that fails must not turn a muted alarm into a published
            # one.
        except (OSError, ValueError):
            action = "unchecked"
        try:
            return publish(action) or action
        except OSError:
            return "failed"
    finally:
        drop_lock(handle)


def forget_and_save(alarm_id, publish=None):
    """Mark an alarm as not true any more, write the state, and publish.

    The key keeps its acknowledgement, so an alarm that was answered
    stays quiet for the rest of the four hours. `publish` cleans the
    board under the board lock, so the board is read, changed and
    written while another writer cannot read it stale.

    The board is cleaned whether the state was written or not: a mute
    state that cannot be locked or read must not leave a stale alarm on
    the board, and the board has its own lock, so it can be cleaned even
    when the mute storage is broken. Return True when the state went to
    the file."""
    written = False
    try:
        with locked():
            state = load_state()
            gone(state, alarm_id)
            written = write_state(merge(load_state(), state))
    except (OSError, ValueError):
        written = False
    if publish is not None:
        # The board is cleaned whether the state was written or not: a
        # mute state that could not be read or locked must not leave a
        # stale alarm on the board.
        publish()
    return written


def main(argv):
    """Quiet one alarm, or show what is quiet, and print what it did.

    `alarms ack <alarm-id> <cause>` records the acknowledgement of that
    one cause, so the coordinator can answer an alarm without taking its
    item off the board. The item stays on the board until the coordinator
    routes it. Only the cause that was answered is quiet: another cause
    of the same alarm was not answered and is not silenced.

    It exits 0 when the acknowledgement was written, 1 when there is no
    raised key for that cause, 2 when the usage is wrong, and 3 when the
    state could not be locked or written. The caller has to say so: an
    acknowledgement that did not reach the file leaves the alarm free to
    raise again on the next tick."""
    if argv[:1] in (["--help"], ["-h"]):
        sys.stdout.write(USAGE)
        return 0
    if argv[:1] == ["status"]:
        try:
            state = load_state()
        except (OSError, ValueError) as error:
            # The state cannot be read, so what is quiet cannot be said.
            # The caller has to know that.
            sys.stderr.write(f"alarms: the mute state could not be read: {error}\n")
            return 3
        if not state:
            print("alarms: no alarm key is recorded")
            return 0
        for key in sorted(state):
            record = entry(state, key)
            until = record.get("until") or "not acknowledged"
            print(f"{key}\n  cause: {record.get('cause', '')}\n  quiet until: {until}")
        return 0
    if len(argv) != 3 or argv[0] != "ack":
        sys.stderr.write(USAGE)
        return 2
    key = key_of(argv[1], argv[2])
    try:
        with locked():
            state = load_state()
            if key not in state:
                sys.stderr.write(f"alarms: no raised key for {key}\n")
                return 1
            acknowledge(state, key)
            if not write_state(merge(load_state(), state)):
                # The acknowledgement did not reach the file, so the alarm
                # will raise again on the next tick. The caller has to say so.
                sys.stderr.write("alarms: the mute state could not be written\n")
                return 3
    except (OSError, ValueError) as error:
        sys.stderr.write(f"alarms: the mute state could not be read or locked: {error}\n")
        return 3
    print(f"alarms: {key} quiet for {MUTE_SECONDS // 3600} hours")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
