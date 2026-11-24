#!/usr/bin/env python3
"""Plain-agent baseline arm: one real model call, no harness rules.

Reads one case JSON on stdin:

    {"id": ..., "kind": ..., "item_text": ..., "options": [...]}

Prints exactly one option, copied verbatim from the list.

There is no coordinator playbook, no AGENTS.md, no skills, no tools and no
system rules beyond "answer one multiple-choice question". This is the
no-rules baseline the harness arm is compared against.

Model route: the cheapest working route on this Mac is Morph DeepSeek V4.1
Flash route through the pi CLI. Override with PLAIN_AGENT_MODEL.
"""

import json
import os
import re
import subprocess
import sys

MODEL = os.environ.get("PLAIN_AGENT_MODEL", "morph/morph-dsv41flash")
SYSTEM = (
    "You answer a single multiple-choice question. "
    "Reply with exactly one option, copied verbatim from the list. "
    "No explanation, no punctuation around it."
)


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ask(item_text, options):
    listing = "\n".join(f"{n}) {o}" for n, o in enumerate(options, 1))
    prompt = f"Question: {item_text}\n\nOptions:\n{listing}\n\nReply with exactly one option."
    cmd = [
        "pi", "-p", "--no-session", "--no-context-files", "--no-skills",
        "--no-extensions", "--no-mcp", "--no-tools", "--model", MODEL,
        "--system-prompt", SYSTEM, prompt,
    ]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return done.stdout.strip()


def choose(reply, options):
    """Map the model's reply to one option, or return the reply unchanged."""
    n = norm(reply)
    if not n:
        return reply
    exact = [o for o in options if norm(o) == n]
    if len(exact) == 1:
        return exact[0]
    # The reply names one option inside a sentence.
    hits = [o for o in options if norm(o) and norm(o) in n]
    if len(hits) == 1:
        return hits[0]
    # A leading number, "option 2", or a bare letter.
    m = re.search(r"\b(?:option\s*)?([1-9])\b", n)
    if m and 1 <= int(m.group(1)) <= len(options):
        return options[int(m.group(1)) - 1]
    return reply.splitlines()[0].strip() if reply.strip() else reply


def main():
    case = json.load(sys.stdin)
    options = case.get("options") or []
    if not options:
        print("")
        return 0
    try:
        reply = ask(case.get("item_text", ""), options)
    except subprocess.TimeoutExpired:
        reply = ""
    print(choose(reply, options))
    return 0


if __name__ == "__main__":
    sys.exit(main())
