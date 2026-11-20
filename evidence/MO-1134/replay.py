#!/usr/bin/env python3
"""Replay the block list rules against a copy of the live providers-blocked.json.

The live file is read, never written: it is copied into a temp COORDQ_DIR and
every write goes to the copy. Run from the repository root:

    python3 evidence/MO-1134/replay.py
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, "coordinator/bin")
import models  # noqa: E402

LIVE = os.path.expanduser("~/Code/coordinator/queue/providers-blocked.json")


def main():
    scratch = tempfile.mkdtemp(prefix="mo1134-")
    store = os.path.join(scratch, models.BLOCKED_FILE)
    shutil.copyfile(LIVE, store)
    os.environ["COORDQ_DIR"] = scratch
    os.environ["COORDINATOR_MODELS"] = "coordinator/models.json"
    before = hashlib.sha256(open(LIVE, "rb").read()).hexdigest()
    now = time.time()

    def write(blocked):
        with open(store, "w") as f:
            json.dump({"blocked": blocked}, f)

    def read():
        with open(store) as f:
            return json.load(f)["blocked"]

    print("== the live file, read through the new reader ==")
    print("now:", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)))
    known = models.known_identities()
    for key, entry in json.load(open(LIVE))["blocked"].items():
        print(f"  {key}: expiry={models.expiry(entry)!r} known={key in known}")
    print("blocked now:", sorted(models.blocked_identities(now=now)))

    print("\n== 1. block_provider writes a numeric expires_at ==")
    models.block_provider({"instanceId": "openai-api", "model": "openai/gpt-6.2-astra"},
                          now + 3600, now=now)
    print(json.dumps(read()["openai-api:gpt-6.2-astra"]))

    print("\n== 2. an until-only entry: a past until is not blocked, a future one is ==")
    past = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now - 60))
    future = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now + 3600))
    write({"openai-api:gpt-6.2-astra": {"by": "provider_block", "until": past}})
    print("past until  ", past, "->", sorted(models.blocked_identities(now=now)))
    write({"openai-api:gpt-6.2-astra": {"by": "provider_block", "until": future}})
    print("future until", future, "->", sorted(models.blocked_identities(now=now)))

    print("\n== 3. a manual block is kept, an unknown-model entry is pruned ==")
    write({"anthropic-api:claude-opus-5-5": {"reason": "credit balance too low"},
           "glm:glm-5.3": {"reason": "weekly limit"},
           "minimax:MiniMax-M3.1-Flash": {"reason": "usage limit"}})
    print("->", sorted(models.blocked_identities(now=now)))

    after = hashlib.sha256(open(LIVE, "rb").read()).hexdigest()
    print("\n== the live file is untouched ==")
    print("sha256 before:", before)
    print("sha256 after: ", after)
    shutil.rmtree(scratch)
    return 0 if before == after else 1


if __name__ == "__main__":
    sys.exit(main())
