#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

for _dir in (Path(__file__).resolve().parent,
             Path(__file__).resolve().parent.parent / "overnight"):
    if (_dir / "journal.py").is_file() or (_dir / "alarms.py").is_file():
        if str(_dir) not in sys.path:
            sys.path.insert(0, str(_dir))

import alarms
import journal

ACTOR = os.environ.get("BOARD_ACTOR", "agent")
decisions = Path(alarms.DECISIONS_PATH)
USAGE = (
    "usage: board.py list\n"
    "       board.py raise '<json>'\n"
    "       board.py remove <id>...\n"
    "       board.py patch <id> key=value..."
)


def holders(alarm_id):
    found = []
    for path in dict.fromkeys((decisions, Path(alarms.board_for(decisions, alarm_id)))):
        board = alarms.read_board(path)[1]
        entry = next((e for e in (board or {"items": []})["items"]
                      if isinstance(e, dict) and e.get("id") == alarm_id), None)
        if entry is not None:
            found.append((path, entry))
    return found


def refuse(verb, alarm_id, why):
    print(f"board: {why}", file=sys.stderr)
    journal.emit("board_refused", ACTOR, verb=verb, id=alarm_id)
    return 1


def refuse_producer(verb, alarm_id):
    return refuse(verb, alarm_id,
                  f"{alarm_id} is owned by its producer; only it withdraws the card")


def cmd_list():
    for path in dict.fromkeys((decisions, Path(alarms.board_for(decisions, "x-MO-0")))):
        for entry in (alarms.read_board(path)[1] or {"items": []})["items"]:
            if isinstance(entry, dict):
                print(f"{entry.get('id')}\t{entry.get('title')}")
    return 0


def cmd_raise(args):
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    item = json.loads(args[0])
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        print("board: raise needs a card object with a string id", file=sys.stderr)
        return 1
    alarm_id = item["id"]
    if alarms.producer_owned(alarm_id):
        return refuse_producer("raise", alarm_id)
    if alarms.route_update(str(decisions), alarm_id, "raise", item) != "wrote":
        print(f"board: {alarm_id} was not written", file=sys.stderr)
        return 1
    journal.emit("board_cli", ACTOR, verb="raise", id=alarm_id, card=item)
    return 0


def cmd_remove(args):
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    owned = [alarm_id for alarm_id in args if alarms.producer_owned(alarm_id)]
    if owned:
        for alarm_id in owned:
            refuse_producer("remove", alarm_id)
        return 1
    for alarm_id in args:
        found = holders(alarm_id)
        if not found:
            print(f"board: {alarm_id} is not on the board", file=sys.stderr)
        for path, held in found:
            if alarms.board_update(path, alarm_id, "remove") != "wrote":
                print(f"board: {alarm_id} was not removed from {path}", file=sys.stderr)
                return 1
            journal.emit("board_cli", ACTOR, verb="remove", id=alarm_id, card=held)
    return 0


def cmd_patch(args):
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    alarm_id = args[0]
    if alarms.producer_owned(alarm_id):
        return refuse_producer("patch", alarm_id)
    fields = {}
    for arg in args[1:]:
        key, sep, value = arg.partition("=")
        if not sep or key == "id":
            return refuse("patch", alarm_id, f"{arg} is not a field to patch")
        fields[key] = value
    found = holders(alarm_id)
    if not found:
        print(f"board: {alarm_id} is not on the board", file=sys.stderr)
        return 1
    path = found[0][0]
    handle = alarms.take_lock(str(path) + ".lock")
    if handle is None:
        print(f"board: {path} could not be locked", file=sys.stderr)
        return 1
    try:
        _, board = alarms.read_board(path)
        entry = None
        if board is not None:
            entry = next((item for item in board["items"]
                          if isinstance(item, dict) and item.get("id") == alarm_id), None)
        if entry is None:
            print(f"board: {alarm_id} is not on the board", file=sys.stderr)
            return 1
        entry.update(fields)
        if not alarms.write_board(path, board):
            print(f"board: {alarm_id} was not patched", file=sys.stderr)
            return 1
    finally:
        alarms.drop_lock(handle)
    journal.emit("board_cli", ACTOR, verb="patch", id=alarm_id, card=entry)
    return 0


def main(argv):
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2
    verb = argv[1]
    if verb == "list":
        return cmd_list()
    if verb == "raise":
        return cmd_raise(argv[2:])
    if verb == "remove":
        return cmd_remove(argv[2:])
    if verb == "patch":
        return cmd_patch(argv[2:])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
