#!/usr/bin/python3
import errno
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time
import tty
from pathlib import Path

REAL = os.path.realpath(str(Path(__file__).with_name("pi.before-mac-ops-12")))
(START, END) = (b"\x1b[200~", b"\x1b[201~")
MARKERS = (
    b"gpt-6.1-terra",
    b"GPT-6.1 Terra",
    b"show full startup help",
    b"thinking max",
    b"thinking off",
    b"thinking high",
    b"thinking medium",
    b"thinking low",
)
(LIMIT, TIMEOUT, SETTLE) = (1 << 20, 45.0, 0.3)
CSI = re.compile(b"\\x1b\\[[\\x30-\\x3f]*[\\x20-\\x2f]*[\\x40-\\x7e]")
OSC = re.compile(b"\\x1b\\].*?(?:\\x07|\\x1b\\\\)", re.DOTALL)


def passthrough(args):
    if "-p" in args or "--print" in args:
        return True
    value_flags = {"--model", "--thinking", "--resume", "--session"}
    flag_only = {
        "--continue",
        "--trust",
        "--no-session",
        "--no-tools",
        "--offline",
    }
    index = 0
    while index < len(args):
        token = args[index]
        if (
            token in value_flags
            and index + 1 < len(args)
            and (not args[index + 1].startswith("-"))
        ):
            index += 2
        elif token in flag_only:
            index += 1
        else:
            return True
    return False


def task_context():
    e = os.environ
    if (
        e.get("HERDR_ENV") != "1"
        or not e.get("HERDR_PROJECTS_ID")
        or (not e.get("HERDR_PROJECTS_TASK_REPORTS"))
    ):
        return False
    try:
        return f"hp-{os.getuid()}" in Path(e.get("TMPDIR", "")).resolve().parts
    except (OSError, RuntimeError):
        return False


def query(seq):
    fixed = {
        b"\x1b[6n": "cpr",
        b"\x1b[?6n": "cpr",
        b"\x1b[5n": "dsr",
        b"\x1b[?5n": "dsr",
        b"\x1b[c": "da",
        b"\x1b[0c": "da",
        b"\x1b[>c": "sda",
        b"\x1b[>0c": "sda",
        b"\x1b[14t": "size",
        b"\x1b[18t": "size",
        b"\x1b[?u": "keys",
        b"\x1b[=u": "keys",
    }
    if seq in fixed:
        return fixed[seq]
    if re.fullmatch(b"\\x1b\\[\\?[0-9;]+\\$p", seq):
        return "mode"
    if seq.startswith(b"\x1b]") and re.match(b"\\x1b\\](?:4|10|11|12);.*\\?", seq):
        return "osc"
    return None


def reply(seq):
    if re.fullmatch(b"\\x1b\\[\\d+;\\d+R", seq):
        return "cpr"
    if re.fullmatch(b"\\x1b\\[\\??\\d+n", seq):
        return "dsr"
    if re.fullmatch(b"\\x1b\\[(?:\\?[0-9;]*|>[0-9;]*)c", seq):
        return "da" if b"?" in seq else "sda"
    if re.fullmatch(b"\\x1b\\[\\?[0-9;]+;[0-9]+\\$y", seq):
        return "mode"
    if re.fullmatch(b"\\x1b\\[(?:4|8);[0-9;]+t", seq):
        return "size"
    if re.fullmatch(b"\\x1b\\[\\?[0-9;]+u", seq):
        return "keys"
    if seq.startswith(b"\x1b]") and re.match(b"\\x1b\\](?:4|10|11|12);", seq):
        return "osc"
    return None


class Queries:
    def __init__(self):
        (self.counts, self.tail) = ({}, b"")

    def observe(self, data):
        (old, all_data) = (len(self.tail), self.tail + data)
        for rx in (CSI, OSC):
            for m in rx.finditer(all_data):
                if m.end() > old:
                    kind = query(m.group())
                    if kind:
                        self.counts[kind] = self.counts.get(kind, 0) + 1
        self.tail = all_data[-256:]

    def take(self, kind):
        if self.counts.get(kind, 0):
            self.counts[kind] -= 1
            return True
        return False


class Input:
    def __init__(self):
        (self.buf, self.paste) = (b"", False)

    def feed(self, data, queries):
        self.buf += data
        (keys, replies, cancel) = (bytearray(), bytearray(), bytearray())
        while self.buf:
            if self.paste:
                i = self.buf.find(END)
                if i < 0:
                    n = max(0, len(self.buf) - len(END) + 1)
                    keys.extend(self.buf[:n])
                    self.buf = self.buf[n:]
                    break
                n = i + len(END)
                keys.extend(self.buf[:n])
                self.buf = self.buf[n:]
                self.paste = False
                continue
            if self.buf.startswith(START):
                keys.extend(START)
                self.buf = self.buf[len(START) :]
                self.paste = True
                continue
            if self.buf[0] == 3:
                cancel.extend(b"\x03")
                self.buf = self.buf[1:]
                continue
            if self.buf.startswith(b"\x1b"):
                if len(self.buf) < 2:
                    break
                if self.buf.startswith(b"\x1b["):
                    end = next(
                        (
                            i + 1
                            for i in range(2, len(self.buf))
                            if 64 <= self.buf[i] <= 126
                        ),
                        None,
                    )
                elif self.buf.startswith(b"\x1b]"):
                    ends = [
                        i + n
                        for (i, n) in (
                            (self.buf.find(b"\x07", 2), 1),
                            (self.buf.find(b"\x1b\\", 2), 2),
                        )
                        if i >= 0
                    ]
                    end = min(ends) if ends else None
                else:
                    end = 2
                if end is None:
                    break
                (seq, self.buf) = (self.buf[:end], self.buf[end:])
                kind = reply(seq)
                (replies if kind and queries.take(kind) else keys).extend(seq)
                continue
            n = next(
                (i for (i, b) in enumerate(self.buf) if b in (3, 27)), len(self.buf)
            )
            keys.extend(self.buf[:n])
            self.buf = self.buf[n:]
        return (bytes(keys), bytes(replies), bytes(cancel))


class Visible:
    def __init__(self):
        (self.state, self.tail) = ("text", bytearray())

    def feed(self, raw):
        out = bytearray()
        for b in raw:
            if self.state == "text":
                if b == 27:
                    self.state = "esc"
                elif b in (10, 13):
                    out.append(32)
                elif b >= 32 and b != 127:
                    out.append(b)
            elif self.state == "esc":
                self.state = (
                    "csi"
                    if b == 91
                    else "string"
                    if b in (93, 80, 94, 95, 88)
                    else "text"
                )
            elif self.state == "csi":
                if 64 <= b <= 126:
                    self.state = "text"
            elif self.state == "string":
                if b == 7:
                    self.state = "text"
                elif b == 27:
                    self.state = "string-esc"
            elif self.state == "string-esc":
                self.state = "text" if b == 92 else "string"
        self.tail.extend(out)
        if len(self.tail) > 32768:
            del self.tail[:-32768]
        return bytes(out)


def stdout(data):
    while data:
        try:
            data = data[os.write(1, data) :]
        except BlockingIOError:
            select.select([], [1], [], 0.1)


def normalized(data):
    return "".join(data.decode("utf-8", "replace").split())


def draft_seen(rendered, suffix, line_count):
    text = normalized(rendered)
    if suffix and suffix.decode("utf-8", "replace") in text:
        return True
    receipt = re.search(r"\[Pastedtext#\d+\+(\d+)lines?\]", text)
    return bool(receipt and receipt.group(1) == str(line_count))


def size(fd):
    try:
        return fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\x00" * 8)
    except OSError:
        return struct.pack("HHHH", 24, 80, 0, 0)


def reap_after_close(pid):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except OSError:
            pass
        end = time.monotonic() + 1.0
        while time.monotonic() < end:
            try:
                (got, status) = os.waitpid(pid, os.WNOHANG)
                if got:
                    return status
            except ChildProcessError:
                return None
            time.sleep(0.05)
    return None


def main():
    args = sys.argv[1:]
    if (
        not os.path.isfile(REAL)
        or not os.access(REAL, os.X_OK)
        or REAL == os.path.realpath(__file__)
    ):
        os.write(
            2,
            b"Pi input gate: original executable is missing; check the install backup.\n",
        )
        return 126
    if (
        passthrough(args)
        or not task_context()
        or (not os.isatty(0))
        or (not os.isatty(1))
    ):
        os.execv(REAL, [REAL, *args])
    (pid, master) = pty.fork()
    if pid == 0:
        os.environ["PI_SKIP_VERSION_CHECK"] = "1"
        try:
            os.execv(REAL, [REAL, *args])
        except OSError as exc:
            os.write(2, f"pi exec failed: {exc}\n".encode())
            os._exit(127)
    stdout(b"\x1b[?2004h")
    old_tty = termios.tcgetattr(0)
    (old_handlers, pending_signal) = ({}, [])
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
        old_handlers[sig] = signal.signal(sig, lambda s, _f: pending_signal.append(s))

    def resize(_s, _f):
        try:
            fcntl.ioctl(master, termios.TIOCSWINSZ, size(1))
            os.killpg(pid, signal.SIGWINCH)
        except OSError:
            pass

    old_handlers[signal.SIGWINCH] = signal.signal(signal.SIGWINCH, resize)
    (inp, queries, visible) = (Input(), Queries(), Visible())
    (startup, candidate, after_paste, to_child, echo) = (
        bytearray(),
        bytearray(),
        bytearray(),
        bytearray(),
        bytearray(),
    )
    ready_at = echo_at = input_at = written_at = None
    paste_left = 0
    ready = sent_paste = session_started = False
    suffix = b""
    paste_lines = 0
    (failure, status, master_eof) = (0, None, False)
    started = time.monotonic()

    def queue(data):
        to_child.extend(data)

    def finish_delivery():
        nonlocal sent_paste, written_at, echo_at, paste_left, input_at, ready_at, ready
        nonlocal suffix, paste_lines
        queue(after_paste)
        after_paste.clear()
        queue(inp.buf)
        inp.buf = b""
        sent_paste = False
        written_at = echo_at = None
        paste_left = 0
        echo.clear()
        input_at = None
        ready_at = None
        ready = False
        suffix = b""
        paste_lines = 0

    def route(data, now):
        nonlocal sent_paste, suffix, input_at, failure, paste_left, paste_lines
        if not data:
            return
        if input_at is None:
            input_at = now
        if not ready:
            (candidate if session_started else startup).extend(data)
            return
        if sent_paste:
            after_paste.extend(data)
            return
        candidate.extend(data)
        start = candidate.find(START)
        if start < 0:
            if not START.startswith(candidate):
                failure = 125
            return
        end = candidate.find(END, start + len(START))
        if end < 0:
            return
        stop = end + len(END)
        raw = bytes(candidate[start + len(START) : end])
        suffix = normalized(raw)[-80:].encode("utf-8")
        paste_lines = raw.count(b"\n") + 1
        queue(candidate[:stop])
        paste_left = len(to_child)
        after_paste.extend(candidate[stop:])
        candidate.clear()
        sent_paste = True
        echo.clear()

    try:
        fcntl.ioctl(master, termios.TIOCSWINSZ, size(1))
        tty.setraw(0, termios.TCSANOW)
        os.set_blocking(master, False)
        while True:
            now = time.monotonic()
            if failure:
                break
            if pending_signal:
                sig = pending_signal.pop(0)
                try:
                    os.killpg(pid, sig)
                except OSError:
                    pass
                failure = 128 + sig
                break
            pending = bool(candidate or startup or inp.buf or sent_paste or after_paste)
            if (not session_started and not ready and now - started > TIMEOUT) or (
                input_at is not None and pending and (now - input_at > TIMEOUT)
            ):
                failure = 124
                break
            if (
                len(startup)
                + len(candidate)
                + len(after_paste)
                + len(to_child)
                + len(inp.buf)
                > LIMIT
            ):
                failure = 125
                break
            visible_norm = b"".join(visible.tail.split()).lower()
            if not ready and any(
                b"".join(m.split()).lower() in visible_norm for m in MARKERS
            ):
                try:
                    canonical_off = not termios.tcgetattr(master)[3] & termios.ICANON
                except (OSError, termios.error):
                    canonical_off = False
                if canonical_off:
                    if ready_at is None:
                        ready_at = now
                    elif now - ready_at >= 0.25:
                        ready = True
                        if session_started:
                            if candidate:
                                route(bytes(candidate), now)
                                candidate.clear()
                        else:
                            route(bytes(startup), now)
                            startup.clear()
                            session_started = True
                else:
                    ready_at = None
            if (
                written_at is not None
                and echo_at is not None
                and (now - max(echo_at, written_at) >= SETTLE)
            ):
                finish_delivery()
            reads = [0] + ([] if master_eof else [master])
            writes = [master] if to_child else []
            (r, w, _) = select.select(reads, writes, [], 0.1)
            if master in r:
                try:
                    raw = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno in (errno.EIO, errno.EBADF):
                        raw = b""
                        master_eof = True
                    elif exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        raw = None
                    else:
                        raise
                if raw == b"":
                    break
                if raw:
                    queries.observe(raw)
                    stdout(raw)
                    stdout(b"\x1b[?2004h")
                    shown = visible.feed(raw)
                    if written_at is not None and echo_at is None:
                        echo.extend(shown)
                        echo[:] = echo[-8192:]
                        if draft_seen(echo, suffix, paste_lines):
                            echo_at = now
                    if (
                        written_at is not None
                        and echo_at is None
                        and now - written_at >= SETTLE
                    ):
                        echo_at = now
            if 0 in r:
                try:
                    raw = os.read(0, 65536)
                except BlockingIOError:
                    raw = None
                if raw == b"":
                    failure = 129
                    break
                if raw:
                    (keys, replies, cancel) = inp.feed(raw, queries)
                    if cancel:
                        failure = 130
                        break
                    queue(replies)
                    route(keys, now)
            if master in w and to_child:
                try:
                    n = os.write(master, to_child[:65536])
                    del to_child[:n]
                    if paste_left:
                        paste_left = max(0, paste_left - n)
                        if paste_left == 0:
                            written_at = time.monotonic()
                            echo.clear()
                except BlockingIOError:
                    pass
            (got, child_status) = os.waitpid(pid, os.WNOHANG)
            if got:
                status = child_status
                if not master_eof:
                    while True:
                        try:
                            raw = os.read(master, 65536)
                        except OSError:
                            break
                        if not raw:
                            break
                        stdout(raw)
                break
    except (OSError, termios.error):
        failure = 125
    finally:
        try:
            os.close(master)
        except OSError:
            pass
        try:
            termios.tcsetattr(0, termios.TCSADRAIN, old_tty)
        except OSError:
            pass
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        try:
            stdout(b"\x1b[?2004l")
        except OSError:
            pass
    if failure:
        reap_after_close(pid)
        if not session_started or (not ready and not sent_paste):
            phase = "before first submit; Enter withheld"
        elif sent_paste or not ready:
            phase = "before follow-up submit; Enter withheld"
        else:
            phase = "mid-session"
        try:
            os.write(2, f"Pi input gate stopped ({failure}) {phase}.\n".encode())
        except OSError:
            pass
        return failure
    if status is None:
        status = reap_after_close(pid)
    code = os.waitstatus_to_exitcode(status) if status is not None else 125
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main())
