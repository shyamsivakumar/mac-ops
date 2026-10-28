#!/usr/bin/env python3
import importlib.machinery
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def load(path):
    loader = importlib.machinery.SourceFileLoader('cursor_gate_checked', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def partitions(data):
    for a in range(len(data) + 1):
        for b in range(a, len(data) + 1):
            yield [data[:a], data[a:b], data[b:]]


def verify(path):
    module = load(path)
    body = 'λ\n'.encode() + b'\x1b[2;3R\x03'
    paste = module.START + body + module.END + b'\x1b[13u'
    terminal_reply = b'\x1b[2;3R'
    stream = terminal_reply + paste + b'\x03'
    count = 0
    for chunks in partitions(stream):
        queries = module.Queries()
        queries.observe(b'\x1b[6n')
        parser = module.Input()
        got = [bytearray(), bytearray(), bytearray()]
        for chunk in chunks:
            for target, part in zip(got, parser.feed(chunk, queries)):
                target.extend(part)
        assert bytes(got[0]) == paste, 'Keyboard or paste bytes changed across chunks'
        assert bytes(got[1]) == terminal_reply, 'Terminal reply changed or was held'
        assert bytes(got[2]) == b'\x03', 'Only the cancellation outside the paste may be separated'
        count += 1
    output = b'\x1b]0;Plan, search, build anything\x07' + b'\x1bPAdd a follow-up\x1b\\' + b'visible \x1b[31mtext\x1b[0m'
    for chunks in partitions(output):
        screen = module.Visible()
        for chunk in chunks:
            screen.feed(chunk)
        assert bytes(screen.tail) == b'visible text', 'Control string content leaked into readiness text'
        count += 1
    receipt = '→ \x1b[36m[Pasted text #7 +68 lines]\x1b[0m'.encode()
    for chunks in partitions(receipt):
        screen = module.Visible()
        for chunk in chunks:
            screen.feed(chunk)
        assert module.draft_seen(screen.tail, b'unseen-body-suffix', 68), 'Folded paste acknowledgement was lost'
        assert not module.draft_seen(screen.tail, b'unseen-body-suffix', 67), 'A different paste line count was accepted'
        count += 1
    hidden = module.Visible()
    hidden.feed(b'\x1b]0;[Pasted text #7 +68 lines]\x07')
    assert not module.draft_seen(hidden.tail, b'unseen-body-suffix', 68), 'An OSC title must not acknowledge a paste'
    query_bytes = b'\x1b[6n\x1b]11;?\x07'
    for chunks in partitions(query_bytes):
        queries = module.Queries()
        for chunk in chunks:
            queries.observe(chunk)
        assert queries.take('cpr') and not queries.take('cpr'), 'Cursor position query counted incorrectly'
        assert queries.take('osc') and not queries.take('osc'), 'OSC query counted incorrectly'
        count += 1
    print(f'PASS: {count} generated input and control-stream chunkings across the actual parser.')
    return count


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Check bounded chunking and control-stream properties against the Cursor input parser.')
    parser.add_argument('source', type=Path, nargs='?', default=Path(__file__).resolve().parents[1] / 'scripts/cursor_agent_gate.py')
    verify(parser.parse_args().source)
