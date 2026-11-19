#!/usr/bin/python3
"""Supervise heavy workloads under macOS host telemetry admission limits."""

from __future__ import annotations

import concurrent.futures
import ctypes
import datetime
import fcntl
import hashlib
import json
import math
import os
import pwd
import re
import signal
import socket
import stat
import subprocess
import sys
import time
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


GIB = 1024**3
MAX_CPU_PCT = 95.0
WARNING_CPU_PCT = 80.0
MAX_MEMORY_PCT = 95.0
MIN_HEADROOM_BYTES = 6 * GIB
HEADROOM_FRACTION = 0.15
PAUSE_HEADROOM_FRACTION = 0.125
SAMPLE_INTERVAL = 2.0
SAMPLE_MAX_AGE = 4.5
NATIVE_TIMEOUT = 2.5
MAX_WAIT_SECONDS = 45 * 60
CRITICAL_LOAD_PER_CORE = 2.0
PRESSURE_HOLD_SECONDS = 15.0
RECOVERY_HOLD_SECONDS = 10.0
PAUSE_REQUEST_SPACING_NS = 5_000_000_000
CAPACITY_MAX_AGE_SECONDS = 30.0
NORMAL_PRESSURE_LEVEL = 1
WARNING_PRESSURE_LEVEL = 2
WARNING_FREE_PERCENT = 30.0
MAX_SWAP_GROWTH_BYTES_PER_SECOND = 1024**2
_SWAP_BASELINE = None
_SWAP_SAMPLE_LOCK = threading.Lock()
CRITICAL_PRESSURE_LEVEL = 4
TERM_GRACE_SECONDS = 5.0
MAX_RUNTIME_SECONDS = 45 * 60
LIMIT_RETRY_NS = 30_000_000_000
LIMIT_EXIT_CODE = 76
WALL_CLOCK_REASON = "wall-clock limit"
RUNTIME_LIMIT_ENV = "HEAVY_MAX_RUNTIME_SECONDS"
WATCHDOG_INTERVAL = 2.0
WATCHDOG_STALE_SECONDS = 6.0
REGISTRY_NAME = "heavy-jobs"
CAPACITY_NAME = "capacity.json"
CONFIG_NAME = "board_governor.json"
HOST_HEADROOM_KEY = "min_headroom_bytes_by_host"
MAX_HOST_HEADROOM_BYTES = 64 * GIB
LEGACY_MARKER_NAME = "legacy-registry.json"
PROTOCOL_RECORD_ID = "0" * 32
LEGACY_SLOTS = Path("/tmp/heavy-slots")
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
QUEUE_FILE_PATTERN = re.compile(r"^queue-([0-9a-f]{32})\.json$")


def monotonic_ns() -> int:
    """Return the monotonic clock reading in nanoseconds."""
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def monotonic() -> float:
    """Return the monotonic clock reading in seconds."""
    return monotonic_ns() / 1_000_000_000.0


class HeavyError(Exception):
    """Base error for supervisor failures reported to the user."""


class TelemetryError(HeavyError):
    """Raised when host telemetry is missing, stale, or invalid."""


@dataclass(frozen=True)
class ProcessInfo:
    """Identity of one process as reported by the process table."""

    pid: int
    ppid: int
    pgid: int
    uid: int
    start_token: str
    start_epoch: float
    state: str


@dataclass(frozen=True)
class Sample:
    """One host telemetry reading used for admission decisions."""

    pressure_level: int
    cpu_busy_pct: float
    memory_used_pct: float
    headroom_bytes: int
    physical_bytes: int
    load_per_core: float
    captured_monotonic: float
    free_percent: Optional[float] = None
    swap_growth_bytes_per_second: Optional[float] = None
    swapout_bytes_per_second: Optional[float] = None
    physical_cores: Optional[int] = None


def _finite_nonnegative(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0


def parse_pressure_level(output: str) -> int:
    """Return the kernel memory pressure level from sysctl output."""
    value = output.strip()
    if value not in ("1", "2", "4"):
        raise TelemetryError("invalid kernel pressure level")
    return int(value)


def parse_vm_stat(output: str) -> Tuple[int, int]:
    """Return the page size and free, inactive, and speculative bytes from vm_stat."""
    page_match = re.search(r"page size of\s+(\d+)\s+bytes", output)
    if not page_match:
        raise TelemetryError("vm_stat omitted page size")
    page_size = int(page_match.group(1))
    pages: Dict[str, int] = {}
    for name in ("free", "inactive", "speculative"):
        match = re.search(
            r"^Pages " + re.escape(name) + r":\s*([0-9,]+)\.?\s*$", output, re.M
        )
        if not match:
            raise TelemetryError("vm_stat omitted required page count")
        pages[name] = int(match.group(1).replace(",", ""))
    if page_size <= 0:
        raise TelemetryError("invalid vm_stat page size")
    return page_size, sum(pages.values()) * page_size


def parse_load(output: str, physical_cores: int) -> float:
    """Return the load average per physical core from uptime output."""
    if physical_cores <= 0:
        raise TelemetryError("invalid physical core count")
    match = re.search(r"load averages?:\s*([0-9]+(?:\.[0-9]+)?)(?:,|\s)", output, re.I)
    if not match:
        raise TelemetryError("uptime omitted load average")
    load = float(match.group(1))
    if not math.isfinite(load) or load < 0:
        raise TelemetryError("invalid load average")
    return load / physical_cores


def parse_cpu_busy(output: str) -> float:
    """Return the user plus system CPU percentage from iostat output."""
    lines = output.splitlines()
    header_index = None
    for index, line in enumerate(lines):
        if re.search(r"\bus\s+sy\s+id\b", line):
            header_index = index
    if header_index is None:
        raise TelemetryError("iostat omitted CPU header")
    row = None
    for line in lines[header_index + 1 :]:
        numbers = re.findall(r"(?<!\S)(\d+(?:\.\d+)?)(?=\s|$)", line)
        if len(numbers) >= 3:
            row = numbers
    if row is None:
        raise TelemetryError("iostat omitted CPU sample")
    user, system, idle = (float(value) for value in row[:3])
    if not all(
        math.isfinite(value) and 0 <= value <= 100 for value in (user, system, idle)
    ):
        raise TelemetryError("invalid iostat CPU sample")
    if abs((user + system + idle) - 100.0) > 5.0:
        raise TelemetryError("inconsistent iostat CPU sample")
    return user + system


def _run_native(argv: Sequence[str], timeout: float = NATIVE_TIMEOUT) -> str:
    try:
        result = subprocess.run(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TelemetryError("native telemetry command failed") from exc
    if result.returncode != 0:
        raise TelemetryError("native telemetry command returned failure")
    return result.stdout


def sample_host(
    *,
    command_runner: Callable[[Sequence[str], float], str] = _run_native,
    clock: Callable[[], float] = monotonic,
) -> Sample:
    """Sample pressure, memory, swap, load, and CPU from native macOS commands."""
    commands = {
        "pressure": ["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
        "memory": ["/usr/sbin/sysctl", "-n", "hw.memsize"],
        "free": ["/usr/bin/memory_pressure", "-Q"],
        "swap": ["/usr/sbin/sysctl", "-n", "vm.swapusage"],
        "cores": ["/usr/sbin/sysctl", "-n", "hw.physicalcpu"],
        "vm": ["/usr/bin/vm_stat"],
        "uptime": ["/usr/bin/uptime"],
        "cpu": ["/usr/sbin/iostat", "-n", "0", "-c", "2", "-w", "1"],
    }
    started = clock()
    outputs: Dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(commands)) as pool:
        futures = {
            key: pool.submit(command_runner, command, NATIVE_TIMEOUT)
            for key, command in commands.items()
        }
        for key, future in futures.items():
            try:
                outputs[key] = future.result(timeout=NATIVE_TIMEOUT + 0.5)
            except Exception as exc:
                for pending in futures.values():
                    pending.cancel()
                raise TelemetryError("host telemetry sample was incomplete") from exc
    captured = clock()
    if captured - started > 3.0:
        raise TelemetryError("host telemetry sample was stale on arrival")
    try:
        pressure = parse_pressure_level(outputs["pressure"])
        physical = int(outputs["memory"].strip())
        cores = int(outputs["cores"].strip())
        if physical <= 0 or cores <= 0:
            raise TelemetryError("invalid physical resource count")
        page_size, headroom = parse_vm_stat(outputs["vm"])
        free_match = re.search(
            r"System-wide memory free percentage:\s*(\d{1,3})%", outputs["free"]
        )
        swap_match = re.search(r"used = ([\d.]+)([KMGT])", outputs["swap"])
        swapout_match = re.search(r"^Swapouts:\s*([0-9,]+)\.?\s*$", outputs["vm"], re.M)
        if not free_match or not swap_match or not swapout_match:
            raise TelemetryError("missing free memory or swap reading")
        free_percent = float(free_match[1])
        if not 0 <= free_percent <= 100:
            raise TelemetryError("invalid free memory percentage")
        swap_used = float(swap_match[1]) * 1024 ** ("KMGT".index(swap_match[2]) + 1)
        if not math.isfinite(swap_used):
            raise TelemetryError("invalid swap usage")
        swapouts = int(swapout_match[1].replace(",", ""))
        load_per_core = parse_load(outputs["uptime"], cores)
        cpu_busy = parse_cpu_busy(outputs["cpu"])
        memory_used = (1.0 - (headroom / physical)) * 100.0
        if not math.isfinite(memory_used) or memory_used < 0 or memory_used > 100:
            raise TelemetryError("invalid memory headroom estimate")
    except (ValueError, KeyError) as exc:
        raise TelemetryError("host telemetry fields were invalid") from exc
    global _SWAP_BASELINE
    swap_growth = swapout_rate = None
    with _SWAP_SAMPLE_LOCK:
        previous = _SWAP_BASELINE
        _SWAP_BASELINE = (captured, swap_used, swapouts, page_size)
        if previous is not None:
            gap = captured - previous[0]
            if 0 < gap <= 10:
                swap_growth = max(0, swap_used - previous[1]) / gap
                if page_size == previous[3] and swapouts >= previous[2]:
                    swapout_rate = (swapouts - previous[2]) * page_size / gap
    return Sample(
        free_percent=free_percent,
        swap_growth_bytes_per_second=swap_growth,
        swapout_bytes_per_second=swapout_rate,
        pressure_level=pressure,
        cpu_busy_pct=cpu_busy,
        memory_used_pct=memory_used,
        headroom_bytes=headroom,
        physical_bytes=physical,
        load_per_core=load_per_core,
        captured_monotonic=captured,
        physical_cores=cores,
    )


def host_config_path() -> Path:
    """Return the path of the installed configuration file beside heavy."""
    return Path(__file__).resolve().parent / CONFIG_NAME


def read_installed_config(path: Path) -> Optional[Dict[str, Any]]:
    """Return the installed configuration, or None when it cannot be trusted.

    The file is opened without following a final symlink and without waiting
    for a writer, and the opened descriptor is checked, so a file swapped
    between the check and the read cannot replace the settings and a pipe
    cannot block the lookup. A file that is too large, malformed, or nested
    deeply enough to exhaust the parser is not usable.
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    fd = None
    try:
        fd = os.open(str(path), flags)
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_mode & 0o022
        ):
            return None
        with os.fdopen(fd, "rb") as handle:
            fd = None
            raw = handle.read(4097)
    except OSError:
        return None
    finally:
        if fd is not None:
            os.close(fd)
    if len(raw) > 4096:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _usable_headroom(value: Any) -> bool:
    """Return True when a configured headroom is a usable byte count."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return 0 < value <= MAX_HOST_HEADROOM_BYTES


def host_headroom_bytes(config_path: Optional[Path] = None) -> int:
    """Return the headroom floor this host needs, or the default 6 GiB floor.

    The installed configuration names hosts and the headroom each one needs.
    Host names are matched without regard to case, so a configured
    ``Shyams-MacBook-Pro.local`` still names the ``shyams-macbook-pro.local``
    host. Two configured names that differ only by case are ambiguous, so
    neither of them is used and that host keeps the default floor. Short-name
    fallback is allowed only when either the configured name or the observed
    hostname is unqualified, so a qualified name never lowers the floor of a
    different qualified host. A missing, unreadable, malformed, or unlisted
    host keeps the default floor.
    """
    path = host_config_path() if config_path is None else Path(config_path)
    value = read_installed_config(path)
    if value is None:
        return MIN_HEADROOM_BYTES
    hosts = value.get(HOST_HEADROOM_KEY)
    if not isinstance(hosts, dict):
        return MIN_HEADROOM_BYTES
    try:
        hostname = socket.gethostname().strip().lower()
    except OSError:
        return MIN_HEADROOM_BYTES
    short_hostname = hostname.split(".")[0]
    host_is_short = "." not in hostname
    exact: Dict[str, Any] = {}
    short: Dict[str, Any] = {}

    def record(mapping: Dict[str, Any], key: str, headroom: Any) -> None:
        if key in mapping:
            mapping[key] = None
        else:
            mapping[key] = headroom

    for name, headroom in hosts.items():
        if not isinstance(name, str) or not name.strip():
            continue
        key = name.strip().lower()
        record(exact, key, headroom)
        if "." not in key or host_is_short:
            record(short, key.split(".")[0], headroom)
    candidates = (hostname, short_hostname)
    for mapping in (exact, short):
        for candidate in candidates:
            headroom = mapping.get(candidate)
            if _usable_headroom(headroom):
                return headroom
    return MIN_HEADROOM_BYTES


def admission_block_reason(
    sample: Sample,
    *,
    now: float,
    active_count: int,
    task_already_active: bool,
    slot_limit: Optional[int] = None,
) -> Optional[str]:
    """Return the reason a sample blocks admission, or None if it admits."""
    values = (
        sample.cpu_busy_pct,
        sample.memory_used_pct,
        sample.headroom_bytes,
        sample.physical_bytes,
        sample.load_per_core,
        sample.captured_monotonic,
    )
    if not all(_finite_nonnegative(value) for value in values):
        return "invalid-telemetry"
    age = now - sample.captured_monotonic
    if age < 0 or age > SAMPLE_MAX_AGE:
        return "stale-telemetry"
    if sample.pressure_level not in (
        NORMAL_PRESSURE_LEVEL,
        WARNING_PRESSURE_LEVEL,
        CRITICAL_PRESSURE_LEVEL,
    ):
        return "invalid-pressure"
    if (
        sample.physical_cores is None
        or isinstance(sample.physical_cores, bool)
        or not isinstance(sample.physical_cores, int)
        or sample.physical_cores <= 0
    ):
        return "invalid-physical-core-count"
    if task_already_active:
        return "task-slot-busy"
    if slot_limit is None:
        return "capacity-unavailable"
    if (
        isinstance(slot_limit, bool)
        or not isinstance(slot_limit, int)
        or slot_limit < 0
    ):
        return "invalid-capacity"
    if active_count >= slot_limit:
        return "global-slots-busy"
    reason = memory_load_block_reason(
        pressure=sample.pressure_level,
        free_percent=sample.free_percent,
        swap_growth=sample.swap_growth_bytes_per_second,
        swapout_rate=sample.swapout_bytes_per_second,
        headroom=sample.headroom_bytes,
        physical=sample.physical_bytes,
    )
    if reason:
        return reason
    if sample.cpu_busy_pct >= MAX_CPU_PCT:
        return "cpu-threshold"
    if sample.memory_used_pct >= MAX_MEMORY_PCT:
        return "memory-threshold"
    return None


def memory_load_block_reason(
    *,
    pressure,
    free_percent,
    swap_growth,
    swapout_rate,
    headroom,
    physical,
    headroom_fraction=HEADROOM_FRACTION,
    min_headroom_bytes=None,
):
    """Return the reason memory blocks admission, or None."""
    if pressure == CRITICAL_PRESSURE_LEVEL:
        return "memory-pressure-critical"
    if pressure not in (NORMAL_PRESSURE_LEVEL, WARNING_PRESSURE_LEVEL):
        return "invalid-pressure"
    rates = (swap_growth, swapout_rate)
    if any(
        _finite_nonnegative(rate) and rate > MAX_SWAP_GROWTH_BYTES_PER_SECOND
        for rate in rates
    ):
        return "swap-growth"
    values = (free_percent, headroom, physical)
    if not all(_finite_nonnegative(value) for value in values):
        return "invalid-telemetry"
    if physical <= 0 or headroom > physical or free_percent > 100:
        return "invalid-telemetry"
    if pressure == WARNING_PRESSURE_LEVEL and free_percent <= WARNING_FREE_PERCENT:
        return "memory-pressure-warning-low-free"
    if not all(_finite_nonnegative(rate) for rate in rates):
        return "first swap sample; normal wait, a few seconds"
    floor = (
        host_headroom_bytes()
        if min_headroom_bytes is None
        else int(min_headroom_bytes)
    )
    if headroom < max(floor, int(physical * headroom_fraction)):
        return "memory-headroom"
    return None


def _start_epoch(token: str) -> float:
    precise = re.fullmatch(r"(\d+)\.(\d{6})", token)
    if precise:
        return float(precise.group(1)) + float(precise.group(2)) / 1_000_000.0
    try:
        return datetime.datetime.strptime(token, "%a %b %d %H:%M:%S %Y").timestamp()
    except (ValueError, OverflowError) as exc:
        raise HeavyError("invalid process start identity") from exc


class _ProcBsdInfo(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint32),
        ("status", ctypes.c_uint32),
        ("xstatus", ctypes.c_uint32),
        ("pid", ctypes.c_uint32),
        ("ppid", ctypes.c_uint32),
        ("uid", ctypes.c_uint32),
        ("gid", ctypes.c_uint32),
        ("ruid", ctypes.c_uint32),
        ("rgid", ctypes.c_uint32),
        ("svuid", ctypes.c_uint32),
        ("svgid", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("comm", ctypes.c_char * 16),
        ("name", ctypes.c_char * 32),
        ("nfiles", ctypes.c_uint32),
        ("pgid", ctypes.c_uint32),
        ("pjobc", ctypes.c_uint32),
        ("tdev", ctypes.c_uint32),
        ("tpgid", ctypes.c_uint32),
        ("nice", ctypes.c_int32),
        ("start_sec", ctypes.c_uint64),
        ("start_usec", ctypes.c_uint64),
    ]


try:
    _LIBPROC = (
        ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        if sys.platform == "darwin"
        else None
    )
except OSError:
    _LIBPROC = None


def _native_process_info(pid: int) -> Optional[ProcessInfo]:
    if sys.platform != "darwin" or _LIBPROC is None:
        raise HeavyError("precise process identity requires macOS libproc")
    function = _LIBPROC.proc_pidinfo
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    function.restype = ctypes.c_int
    info = _ProcBsdInfo()
    size = ctypes.sizeof(info)
    received = function(pid, 3, 0, ctypes.byref(info), size)
    if received == 0:
        return None
    if received != size or info.pid != pid:
        raise HeavyError("macOS process identity response was incomplete")
    token = "{}.{:06d}".format(info.start_sec, info.start_usec)
    return ProcessInfo(
        pid=int(info.pid),
        ppid=int(info.ppid),
        pgid=int(info.pgid),
        uid=int(info.uid),
        start_token=token,
        start_epoch=float(info.start_sec) + float(info.start_usec) / 1_000_000.0,
        state="",
    )


def _parse_process_table(output: str) -> Dict[int, ProcessInfo]:
    result: Dict[int, ProcessInfo] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        match = re.match(
            r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(\S+)\s+(.+?)\s*$", line
        )
        if not match:
            raise HeavyError("process identity sample was malformed")
        pid, ppid, pgid, uid = (int(match.group(index)) for index in range(1, 5))
        state = match.group(5)
        token = match.group(6).strip()
        result[pid] = ProcessInfo(
            pid, ppid, pgid, uid, token, _start_epoch(token), state
        )
    return result


def process_table(
    *, command_runner: Callable[[Sequence[str], float], str] = _run_native
) -> Dict[int, ProcessInfo]:
    """Return the process table keyed by pid with precise start tokens for own processes."""
    output = command_runner(
        ["/bin/ps", "-axo", "pid=,ppid=,pgid=,uid=,stat=,lstart="],
        NATIVE_TIMEOUT,
    )
    rows = _parse_process_table(output)
    for pid, row in list(rows.items()):
        if row.uid == os.getuid():
            precise = _native_process_info(pid)
            if precise is None:
                rows.pop(pid, None)
            else:
                rows[pid] = ProcessInfo(
                    precise.pid,
                    precise.ppid,
                    precise.pgid,
                    precise.uid,
                    precise.start_token,
                    precise.start_epoch,
                    row.state,
                )
    return rows


def kernel_boot_identity(
    *, command_runner: Callable[[Sequence[str], float], str] = _run_native
) -> str:
    """Return the kernel boot time in seconds, used as the boot identity."""
    output = command_runner(["/usr/sbin/sysctl", "-n", "kern.boottime"], NATIVE_TIMEOUT)
    match = re.search(r"sec\s*=\s*(\d+)", output)
    if not match:
        raise HeavyError("kernel boot identity unavailable")
    return match.group(1)


def _secure_directory(path: Path, uid: int, *, create: bool, mode: int) -> None:
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        if not create:
            raise HeavyError("required state directory is missing")
        os.mkdir(str(path), mode)
        info = os.lstat(str(path))
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise HeavyError("state directory is not a real directory")
    if info.st_uid != uid or info.st_mode & 0o022:
        raise HeavyError("state directory ownership or permissions are unsafe")
    if mode == 0o700 and info.st_mode & 0o077:
        raise HeavyError("private state directory permissions are unsafe")


def state_directory(*, uid: Optional[int] = None) -> Path:
    """Return the secured per-user registry directory, creating it if needed."""
    user_id = os.getuid() if uid is None else uid
    try:
        home = Path(pwd.getpwuid(user_id).pw_dir)
    except KeyError as exc:
        raise HeavyError("user home directory is unavailable") from exc
    if not home.is_absolute() or os.path.realpath(str(home)) != str(home):
        raise HeavyError("user home directory is not canonical")
    _secure_directory(home, user_id, create=False, mode=0o755)
    local_state = home / ".local"
    _secure_directory(local_state, user_id, create=True, mode=0o755)
    state_root = local_state / "state"
    _secure_directory(state_root, user_id, create=True, mode=0o700)
    owner = state_root / "mac-ops"
    _secure_directory(owner, user_id, create=True, mode=0o700)
    jobs = owner / REGISTRY_NAME
    _secure_directory(jobs, user_id, create=True, mode=0o700)
    return jobs


def _read_capacity_config(
    registry: "Registry",
    *,
    now: Optional[float] = None,
    boot_id: Optional[str] = None,
) -> Dict[str, Any]:
    _secure_directory(registry.directory.parent, registry.uid, create=False, mode=0o700)
    path = registry.directory.parent / CAPACITY_NAME
    try:
        info = os.lstat(str(path))
    except OSError as exc:
        raise TelemetryError("capacity contract is unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != registry.uid
        or info.st_mode & 0o077
    ):
        raise TelemetryError("capacity contract is unsafe")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != registry.uid
            or opened.st_mode & 0o077
        ):
            os.close(fd)
            raise TelemetryError("capacity contract is unsafe")
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read(4097)
    except OSError as exc:
        raise TelemetryError("capacity contract could not be read") from exc
    if len(raw) > 4096:
        raise TelemetryError("capacity contract is too large")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryError("capacity contract is malformed") from exc
    if not isinstance(value, dict):
        raise TelemetryError("capacity contract is malformed")
    slots = value.get("heavy_slots")
    updated_at = value.get("updated_at")
    reported_boot = value.get("boot_id")
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 0:
        raise TelemetryError("capacity slot count is invalid")
    if (
        isinstance(updated_at, bool)
        or not isinstance(updated_at, (int, float))
        or not math.isfinite(float(updated_at))
    ):
        raise TelemetryError("capacity timestamp is invalid")
    if not isinstance(reported_boot, str) or not reported_boot:
        raise TelemetryError("capacity boot identity is invalid")
    current_time = time.time() if now is None else now
    age = current_time - float(updated_at)
    if (
        not math.isfinite(current_time)
        or not math.isfinite(age)
        or age < 0
        or age > CAPACITY_MAX_AGE_SECONDS
    ):
        raise TelemetryError("capacity contract is stale")
    if boot_id is not None and reported_boot != boot_id:
        raise TelemetryError("capacity contract belongs to another boot")
    return value


def _effective_slot_limit(
    registry: "Registry",
    sample: Sample,
    *,
    now: Optional[float] = None,
    boot_id: Optional[str] = None,
) -> int:
    value = _read_capacity_config(registry, now=now, boot_id=boot_id)
    cores = sample.physical_cores
    physical_bytes = sample.physical_bytes
    if isinstance(cores, bool) or not isinstance(cores, int) or cores <= 0:
        raise TelemetryError("physical core count is unavailable")
    if (
        isinstance(physical_bytes, bool)
        or not isinstance(physical_bytes, int)
        or physical_bytes <= 0
    ):
        raise TelemetryError("physical memory size is unavailable")
    memory_limit = physical_bytes // (6 * GIB)
    return min(int(value["heavy_slots"]), cores, memory_limit)


def _legacy_draining(registry: "Registry") -> bool:
    marker = registry.directory.parent / LEGACY_MARKER_NAME
    try:
        info = os.lstat(str(marker))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != registry.uid
        or info.st_mode & 0o077
    ):
        return True
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(marker), flags)
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != registry.uid
            or opened.st_mode & 0o077
        ):
            os.close(fd)
            return True
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read(4097)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return True
    if (
        len(raw) > 4096
        or not isinstance(value, dict)
        or not isinstance(value.get("path"), str)
        or not Path(value["path"]).is_absolute()
        or os.path.realpath(value["path"]) != value["path"]
    ):
        return True
    try:
        home = Path(pwd.getpwuid(registry.uid).pw_dir)
    except KeyError:
        return True
    expected = os.path.realpath(str(home / ".multica-codex" / REGISTRY_NAME))
    if value["path"] != expected:
        return True
    return True


class Registry:
    """Persist job, queue, and heartbeat records in one secured directory."""

    def __init__(self, directory: Path, *, uid: Optional[int] = None):
        """Bind the registry to a directory and the expected owner uid."""
        self.directory = Path(directory)
        self.uid = os.getuid() if uid is None else uid

    @contextmanager
    def lock(self, *, exclusive: bool = True, timeout: float = 5.0) -> Iterable[None]:
        """Hold a flock on the registry lock file for the duration of the block."""
        _secure_directory(self.directory, self.uid, create=False, mode=0o700)
        lock_path = self.directory / ".lock"
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(lock_path), flags, 0o600)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != self.uid
                or info.st_mode & 0o077
            ):
                raise HeavyError("registry lock file is unsafe")
            operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            deadline = monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, operation | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if monotonic() >= deadline:
                        raise HeavyError("registry lock timed out")
                    time.sleep(0.05)
            yield
        finally:
            os.close(fd)

    def _job_dir(self, job_id: str) -> Path:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise HeavyError("invalid job identity")
        path = self.directory / job_id
        _secure_directory(path, self.uid, create=False, mode=0o700)
        return path

    def _read_record(self, job_id: str) -> Dict[str, Any]:
        path = self._job_dir(job_id) / "record.json"
        info = os.lstat(str(path))
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != self.uid
            or info.st_mode & 0o077
        ):
            raise HeavyError("registry record is unsafe")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(path), flags)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise HeavyError("registry record is too large")
        value = json.loads(raw)
        if job_id == PROTOCOL_RECORD_ID:
            if (
                not isinstance(value, dict)
                or value.get("schema") != 2
                or value.get("kind") != "registry-protocol"
                or value.get("clock") != "CLOCK_MONOTONIC"
                or value.get("job_id") != job_id
                or value.get("uid") != self.uid
            ):
                raise HeavyError("registry protocol fence is invalid")
            return value
        if (
            not isinstance(value, dict)
            or value.get("schema") != 1
            or value.get("clock") != "CLOCK_MONOTONIC"
            or value.get("job_id") != job_id
        ):
            raise HeavyError("registry record identity is invalid")
        if value.get("uid") != self.uid:
            raise HeavyError("registry record owner is invalid")
        return value

    def _write_record(self, record: Dict[str, Any]) -> None:
        job_id = record.get("job_id")
        directory = self._job_dir(job_id)
        target = directory / "record.json"
        try:
            info = os.lstat(str(target))
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != self.uid
                or info.st_mode & 0o077
            ):
                raise HeavyError("registry record is unsafe")
        except FileNotFoundError:
            pass
        temp = directory / (".record-" + uuid.uuid4().hex + ".tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(temp), flags, 0o600)
        try:
            data = json.dumps(record, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise HeavyError("registry write made no progress")
                view = view[written:]
            os.fsync(fd)
        except Exception:
            os.close(fd)
            try:
                os.unlink(str(temp))
            except OSError:
                pass
            raise
        else:
            os.close(fd)
        os.replace(str(temp), str(target))
        dir_fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def _job_ids(self) -> List[str]:
        return sorted(
            item
            for item in os.listdir(str(self.directory))
            if JOB_ID_PATTERN.fullmatch(item)
        )

    def records(self) -> List[Dict[str, Any]]:
        """Return all job records except the protocol record."""
        rows = [self._read_record(job_id) for job_id in self._job_ids()]
        return [row for row in rows if row["job_id"] != PROTOCOL_RECORD_ID]

    def ensure_protocol(self) -> None:
        """Create the protocol record if it does not exist."""
        with self.lock():
            if os.path.lexists(str(self.directory / PROTOCOL_RECORD_ID)):
                self._read_record(PROTOCOL_RECORD_ID)
            else:
                self.create(
                    {
                        "schema": 2,
                        "kind": "registry-protocol",
                        "job_id": PROTOCOL_RECORD_ID,
                        "uid": self.uid,
                        "clock": "CLOCK_MONOTONIC",
                    }
                )

    def create(self, record: Dict[str, Any]) -> None:
        """Create a job directory and write its initial record."""
        job_id = record["job_id"]
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise HeavyError("invalid job identity")
        directory = self.directory / job_id
        os.mkdir(str(directory), 0o700)
        try:
            self._write_record(record)
        except Exception:
            try:
                os.rmdir(str(directory))
            except OSError:
                pass
            raise

    def update(
        self, job_id: str, mutator: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]
    ) -> Optional[Dict[str, Any]]:
        """Apply mutator to a job record and persist the result if it returns one."""
        record = self._read_record(job_id)
        updated = mutator(dict(record))
        if updated is None:
            return None
        self._write_record(updated)
        return updated

    def remove(self, job_id: str) -> None:
        """Delete a job's record and heartbeat files and its directory."""
        directory = self._job_dir(job_id)
        for name in ("record.json", "heartbeat"):
            path = directory / name
            try:
                info = os.lstat(str(path))
            except FileNotFoundError:
                continue
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != self.uid
                or info.st_mode & 0o077
            ):
                raise HeavyError("refusing to remove unsafe registry file")
            os.unlink(str(path))
        if os.listdir(str(directory)):
            raise HeavyError("refusing to remove unexpected registry files")
        os.rmdir(str(directory))

    def write_heartbeat(self, job_id: str, monotonic_ns: int) -> None:
        """Atomically write a monotonic heartbeat timestamp for a job."""
        directory = self._job_dir(job_id)
        path = directory / "heartbeat"
        temp = directory / (".heartbeat-" + uuid.uuid4().hex + ".tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(temp), flags, 0o600)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != self.uid
                or info.st_mode & 0o077
            ):
                raise HeavyError("heartbeat file is unsafe")
            os.write(fd, str(monotonic_ns).encode("ascii"))
            os.fsync(fd)
        except Exception:
            os.close(fd)
            try:
                os.unlink(str(temp))
            except OSError:
                pass
            raise
        else:
            os.close(fd)
        os.replace(str(temp), str(path))
        dir_fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def read_heartbeat(self, job_id: str) -> Optional[int]:
        """Return the job's heartbeat timestamp, or None if it is missing or unsafe."""
        path = self._job_dir(job_id) / "heartbeat"
        try:
            info = os.lstat(str(path))
        except FileNotFoundError:
            return None
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != self.uid
            or info.st_mode & 0o077
        ):
            return None
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(path), flags)
        try:
            raw = os.read(fd, 64).decode("ascii").strip()
        finally:
            os.close(fd)
        if not raw.isdigit():
            return None
        return int(raw)

    def _queue_path(self, queue_id: str) -> Path:
        if not JOB_ID_PATTERN.fullmatch(queue_id):
            raise HeavyError("invalid queue identity")
        return self.directory / ("queue-" + queue_id + ".json")

    def queue_records(self) -> List[Dict[str, Any]]:
        """Return validated queue records from the registry directory."""
        rows = []
        for name in os.listdir(str(self.directory)):
            match = QUEUE_FILE_PATTERN.fullmatch(name)
            if not match:
                continue
            queue_id = match.group(1)
            path = self._queue_path(queue_id)
            info = os.lstat(str(path))
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != self.uid
                or info.st_mode & 0o077
            ):
                raise HeavyError("queue record is unsafe")
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(str(path), flags)
            with os.fdopen(fd, "rb") as handle:
                raw = handle.read(65537)
            if len(raw) > 65536:
                raise HeavyError("queue record is too large")
            value = json.loads(raw.decode("utf-8"))
            if (
                not isinstance(value, dict)
                or value.get("schema") != 1
                or value.get("kind") != "queue"
                or value.get("queue_id") != queue_id
                or value.get("uid") != self.uid
                or value.get("role") not in ("ordinary", "review", "deploy")
                or isinstance(value.get("created_ns"), bool)
                or not isinstance(value.get("created_ns"), int)
                or value.get("created_ns") < 0
                or not isinstance(value.get("boot_id"), str)
                or not value.get("boot_id")
                or not isinstance(value.get("process"), dict)
                or not isinstance(value.get("task_key"), str)
                or not isinstance(value.get("task_id"), str)
                or not isinstance(value.get("command_basename"), str)
            ):
                raise HeavyError("queue record identity is invalid")
            process = value["process"]
            if (
                isinstance(process.get("pid"), bool)
                or not isinstance(process.get("pid"), int)
                or process.get("pid") <= 0
                or process.get("uid") != self.uid
                or not isinstance(process.get("start"), str)
                or process.get("boot_id") != value.get("boot_id")
                or process.get("task_key") != value.get("task_key")
            ):
                raise HeavyError("queue process identity is invalid")
            rows.append(value)
        return rows

    def create_queue(self, record: Dict[str, Any]) -> None:
        """Atomically write a queue record to the registry directory."""
        queue_id = record.get("queue_id")
        path = self._queue_path(queue_id)
        temp = self.directory / (".queue-" + queue_id + ".tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(temp), flags, 0o600)
        try:
            data = json.dumps(record, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise HeavyError("queue write made no progress")
                view = view[written:]
            os.fsync(fd)
        except Exception:
            os.close(fd)
            try:
                os.unlink(str(temp))
            except OSError:
                pass
            raise
        else:
            os.close(fd)
        os.replace(str(temp), str(path))
        dir_fd = os.open(str(self.directory), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def remove_queue(self, queue_id: str) -> None:
        """Delete a queue record if it exists and is safe to remove."""
        path = self._queue_path(queue_id)
        try:
            info = os.lstat(str(path))
        except FileNotFoundError:
            return
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != self.uid
            or info.st_mode & 0o077
        ):
            raise HeavyError("refusing to remove unsafe queue record")
        os.unlink(str(path))

    def update_queue(
        self,
        queue_id: str,
        mutator: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        """Apply mutator to a queue record and persist the result if it returns one."""
        path = self._queue_path(queue_id)
        try:
            info = os.lstat(str(path))
        except FileNotFoundError:
            return None
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != self.uid
            or info.st_mode & 0o077
        ):
            raise HeavyError("refusing to update unsafe queue record")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(path), flags)
        try:
            raw = os.read(fd, 65537)
        finally:
            os.close(fd)
        if len(raw) > 65536:
            raise HeavyError("queue record is too large")
        record = json.loads(raw.decode("utf-8"))
        updated = mutator(dict(record))
        if updated is None:
            return None
        self.create_queue(updated)
        return updated


def legacy_slot_count(
    table: Dict[int, ProcessInfo], *, root: Path = LEGACY_SLOTS
) -> int:
    """Count legacy slots that hold a live or unverifiable pid."""
    try:
        flags = (
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        root_fd = os.open(str(root), flags)
    except FileNotFoundError:
        return 0
    try:
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            raise HeavyError("legacy slot state is unsafe")
        count = 0
        for name in os.listdir(root_fd):
            if not re.fullmatch(r"slot-\d+", name):
                continue
            try:
                slot_fd = os.open(name, flags, dir_fd=root_fd)
            except FileNotFoundError:
                continue
            try:
                if not stat.S_ISDIR(os.fstat(slot_fd).st_mode):
                    raise HeavyError("legacy slot entry is unsafe")
                pid_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                try:
                    fd = os.open("pid", pid_flags, dir_fd=slot_fd)
                except FileNotFoundError:
                    count += 1
                    continue
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise HeavyError("legacy slot pid record is unsafe")
                    raw = os.read(fd, 64).decode("ascii").strip()
                finally:
                    os.close(fd)
            finally:
                os.close(slot_fd)
            if not raw.isdigit():
                count += 1
                continue
            if int(raw) in table:
                count += 1
        return count
    finally:
        os.close(root_fd)


def _identity_matches(info: Optional[ProcessInfo], identity: Dict[str, Any]) -> bool:
    if info is None:
        return False
    if (
        info.pid != identity.get("pid")
        or info.uid != identity.get("uid")
        or info.start_token != identity.get("start")
    ):
        return False
    return True


def _verified_group_members(
    identity: Dict[str, Any],
    table: Dict[int, ProcessInfo],
    *,
    getpgid: Callable[[int], int] = os.getpgid,
    getsid: Callable[[int], int] = os.getsid,
) -> Optional[List[ProcessInfo]]:
    pid = int(identity["pid"])
    uid = int(identity["uid"])
    pgid = int(identity["pgid"])
    start_token = str(identity["start"])
    start_epoch = _start_epoch(start_token)
    root = table.get(pid)
    if root is not None and (
        root.uid != uid or root.start_token != start_token or root.pgid != pgid
    ):
        return None
    root_live = root is not None and not root.state.startswith(("Z", "X"))
    members = [row for row in table.values() if row.pgid == pgid]
    verified = []
    for row in members:
        if row.state.startswith(("Z", "X")):
            continue
        if row.uid != uid or row.start_epoch < start_epoch:
            return None
        try:
            if getpgid(row.pid) != pgid or getsid(row.pid) != pid:
                return None
        except OSError:
            continue
        verified.append(row)
    if root_live and all(row.pid != pid for row in verified):
        return None
    return verified


def _workload_identity(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    value = record.get("workload")
    return value if isinstance(value, dict) else None


def _record_live(
    record: Dict[str, Any], table: Dict[int, ProcessInfo]
) -> Tuple[bool, bool]:
    supervisor = record.get("supervisor")
    supervisor_alive = bool(
        supervisor and _identity_matches(table.get(supervisor.get("pid")), supervisor)
    )
    workload = _workload_identity(record)
    if workload is None:
        return supervisor_alive, supervisor_alive
    members = _verified_group_members(workload, table)
    if members is None:
        return True, supervisor_alive
    return bool(members) or supervisor_alive, supervisor_alive


def _log_event(
    directory: Path, event: str, record: Dict[str, Any], *, detail: Optional[str] = None
) -> None:
    entry = {
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "event": event,
        "job_id": record.get("job_id"),
        "task_id": record.get("task_id"),
        "command": record.get("command_basename"),
        "role": record.get("role", "ordinary"),
        "queue_id": record.get("queue_id"),
        "supervisor": record.get("supervisor", record.get("process")),
        "workload": record.get("workload"),
    }
    if detail:
        entry["detail"] = detail
    path = directory / "events.jsonl"
    flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise HeavyError("event log is unsafe")
        os.write(
            fd,
            (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            ),
        )
    finally:
        os.close(fd)


def _task_identity(
    *,
    environ: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    uid: Optional[int] = None,
) -> Tuple[str, str]:
    env = os.environ if environ is None else environ
    user_id = os.getuid() if uid is None else uid
    project_id = env.get("HERDR_PROJECTS_ID", "").strip()
    if project_id:
        if not TASK_ID_PATTERN.fullmatch(project_id) or ".." in project_id.split("/"):
            raise HeavyError("HERDR_PROJECTS_ID has an invalid task identity")
        return "board:" + project_id, project_id
    canonical = os.path.realpath(cwd if cwd is not None else os.getcwd())
    digest = hashlib.sha256(
        (str(user_id) + "\0" + canonical).encode("utf-8")
    ).hexdigest()
    return "manual:" + digest, "manual:" + digest[:16]


def _supervisor_identity(
    task_key: str, boot_id: str, table: Dict[int, ProcessInfo], uid: int
) -> Dict[str, Any]:
    info = table.get(os.getpid())
    if info is None or info.uid != uid:
        raise HeavyError("supervisor process identity unavailable")
    return {
        "pid": info.pid,
        "start": info.start_token,
        "uid": info.uid,
        "boot_id": boot_id,
        "task_key": task_key,
    }


def _workload_identity_from_process(
    pid: int,
    task_key: str,
    boot_id: str,
    table: Dict[int, ProcessInfo],
    *,
    getpgid: Callable[[int], int] = os.getpgid,
    getsid: Callable[[int], int] = os.getsid,
) -> Dict[str, Any]:
    info = table.get(pid)
    if info is None or info.uid != os.getuid() or info.pgid != pid:
        raise HeavyError("workload process group identity unavailable")
    try:
        if getpgid(pid) != pid or getsid(pid) != pid:
            raise HeavyError("workload did not start in an isolated process group")
    except OSError as exc:
        raise HeavyError("workload process identity could not be verified") from exc
    return {
        "pid": info.pid,
        "start": info.start_token,
        "uid": info.uid,
        "pgid": info.pgid,
        "boot_id": boot_id,
        "task_key": task_key,
    }


def _claim_termination(
    registry: Registry,
    job_id: str,
    reason: str,
    *,
    claimant_pid: int,
    expected_workload: Optional[Dict[str, Any]] = None,
    takeover: bool = False,
    observed_termination: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    with registry.lock():

        def change(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            workload = _workload_identity(record)
            if record.get("state") in ("complete", "removed"):
                return None
            if expected_workload is not None and workload != expected_workload:
                return None
            if (
                workload is None
                or record.get("task_key") != workload.get("task_key")
                or record.get("uid") != workload.get("uid")
            ):
                return None
            if workload.get("boot_id") != record.get("supervisor", {}).get("boot_id"):
                return None
            existing = record.get("termination")
            if existing and not takeover:
                return None
            if (
                existing
                and observed_termination is not None
                and any(
                    existing.get(key) != observed_termination.get(key)
                    for key in ("claimant_pid", "requested_ns", "takeover_ns")
                )
            ):
                return None
            if existing:
                existing["claimant_pid"] = claimant_pid
                existing["takeover_ns"] = monotonic_ns()
                record["termination"] = existing
            else:
                record["termination"] = {
                    "reason": reason,
                    "claimant_pid": claimant_pid,
                    "requested_ns": monotonic_ns(),
                }
            record["state"] = "terminating"
            return record

        return registry.update(job_id, change)


def _set_curtail_request_locked(
    registry: Registry, job_id: str, reason: str, source: str
) -> Optional[Dict[str, Any]]:
    def change(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if (
            record.get("state") in ("complete", "removed")
            or record.get("curtail_request")
            or record.get("termination")
        ):
            return None
        record["curtail_request"] = {
            "reason": reason,
            "source": source,
            "requested_ns": monotonic_ns(),
        }
        record["state"] = "curtail-requested"
        return record

    return registry.update(job_id, change)


def _clear_curtail_request(registry: Registry, job_id: str) -> None:
    with registry.lock():

        def change(record: Dict[str, Any]) -> Dict[str, Any]:
            request = record.get("curtail_request") or {}
            if request.get("source") == "host-alarm":
                record.pop("curtail_request", None)
                if record.get("state") == "curtail-requested":
                    record["state"] = "running"
            return record

        registry.update(job_id, change)


def _record(registry: Registry, job_id: str) -> Dict[str, Any]:
    with registry.lock(exclusive=False):
        return registry._read_record(job_id)


def _mark_complete(
    registry: Registry, job_id: str, *, state: str = "complete"
) -> Optional[Dict[str, Any]]:
    with registry.lock():

        def change(record: Dict[str, Any]) -> Dict[str, Any]:
            record["state"] = state
            return record

        return registry.update(job_id, change)


def _safe_group_members(
    identity: Dict[str, Any],
    *,
    table_reader: Callable[[], Dict[int, ProcessInfo]] = process_table,
    getpgid: Callable[[int], int] = os.getpgid,
    getsid: Callable[[int], int] = os.getsid,
    boot_reader: Callable[[], str] = kernel_boot_identity,
) -> Optional[List[ProcessInfo]]:
    try:
        if boot_reader() != identity.get("boot_id"):
            return None
        table = table_reader()
    except Exception:
        return None
    return _verified_group_members(identity, table, getpgid=getpgid, getsid=getsid)


def terminate_owned_group(
    identity: Dict[str, Any],
    *,
    reason: str,
    signal_group: Callable[[int, int], None] = os.killpg,
    sleep: Callable[[float], None] = time.sleep,
    table_reader: Callable[[], Dict[int, ProcessInfo]] = process_table,
    getpgid: Callable[[int], int] = os.getpgid,
    getsid: Callable[[int], int] = os.getsid,
    boot_reader: Callable[[], str] = kernel_boot_identity,
    grace_seconds: float = TERM_GRACE_SECONDS,
) -> bool:
    """Send SIGTERM then SIGKILL to an owned process group and return True once it is gone."""
    if (
        identity.get("uid") != os.getuid()
        or not identity.get("task_key")
        or identity.get("pid") != identity.get("pgid")
        or not identity.get("boot_id")
    ):
        return False
    members = _safe_group_members(
        identity,
        table_reader=table_reader,
        getpgid=getpgid,
        getsid=getsid,
        boot_reader=boot_reader,
    )
    if members is None:
        return False
    if not members:
        return True
    try:
        signal_group(int(identity["pgid"]), signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    sleep(grace_seconds)
    members = _safe_group_members(
        identity,
        table_reader=table_reader,
        getpgid=getpgid,
        getsid=getsid,
        boot_reader=boot_reader,
    )
    if members is None:
        return False
    if not members:
        return True
    try:
        signal_group(int(identity["pgid"]), signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    deadline = monotonic() + 2.0
    while monotonic() < deadline:
        members = _safe_group_members(
            identity,
            table_reader=table_reader,
            getpgid=getpgid,
            getsid=getsid,
            boot_reader=boot_reader,
        )
        if members == []:
            return True
        if members is None:
            return False
        sleep(0.2)
    return False


def _write_request_for_newest(registry: Registry) -> Dict[str, Any]:
    with registry.lock():
        records = registry.records()
        active = [
            record
            for record in records
            if record.get("state") not in ("complete", "removed")
        ]
        if not active:
            return {"requested": False, "reason": "no-active-jobs"}
        if any(
            record.get("curtail_request") or record.get("termination")
            for record in active
        ):
            return {"requested": False, "reason": "curtail-already-pending"}
        newest = max(active, key=lambda record: int(record.get("created_ns", 0)))
        changed = _set_curtail_request_locked(
            registry, newest["job_id"], "external-request", "external-request"
        )
        if changed is None:
            return {"requested": False, "reason": "curtail-already-pending"}
        return {
            "requested": True,
            "job_id": newest["job_id"],
            "task_id": newest.get("task_id"),
            "command": newest.get("command_basename"),
        }


def status_payload(
    registry: Registry,
    *,
    sample_reader: Callable[[], Sample] = sample_host,
    boot_reader: Callable[[], str] = kernel_boot_identity,
) -> Dict[str, Any]:
    """Return the registry status payload with limits, pauses, and queue state."""
    with registry.lock(exclusive=False):
        records = registry.records()
        queues = registry.queue_records()
        try:
            protocol = registry._read_record(PROTOCOL_RECORD_ID)
        except Exception:
            protocol = {}
    records.sort(key=lambda record: int(record.get("created_ns", 0)), reverse=True)
    queues.sort(key=_queue_sort_key)
    try:
        sample = sample_reader()
        global_limit = _effective_slot_limit(
            registry, sample, now=time.time(), boot_id=boot_reader()
        )
    except Exception:
        global_limit = None
    return {
        "schema": 1,
        "clock": "CLOCK_MONOTONIC",
        "global_limit": global_limit,
        "global_pause": {
            "last_requested_ns": protocol.get("last_pause_request_ns"),
            "last_job_id": protocol.get("last_pause_job_id"),
            "selection": protocol.get("last_pause_selection"),
        },
        "legacy_draining": _legacy_draining(registry),
        "activation_pending": os.path.lexists(
            str(registry.directory / ".activation-pending")
        ),
        "queue": [
            {
                "queue_id": row.get("queue_id"),
                "task_id": row.get("task_id"),
                "command": row.get("command_basename"),
                "role": row.get("role"),
                "position": index + 1,
                "created_ns": row.get("created_ns"),
            }
            for index, row in enumerate(queues)
        ],
        "jobs": [
            {
                "job_id": row.get("job_id"),
                "task_id": row.get("task_id"),
                "command": row.get("command_basename"),
                "role": row.get("role", "ordinary"),
                "state": row.get("state"),
                "created_ns": row.get("created_ns"),
                "supervisor": row.get("supervisor"),
                "workload": row.get("workload"),
                "pause": row.get("pause"),
                "curtail_request": row.get("curtail_request"),
                "termination": row.get("termination"),
            }
            for row in records
        ],
    }


def _prune_finished_locked(
    registry: Registry,
    records: List[Dict[str, Any]],
    table: Dict[int, ProcessInfo],
    snapshot_started_ns: int,
    boot_id: str,
) -> None:
    for record in records:
        supervisor = record.get("supervisor")
        if not isinstance(supervisor, dict):
            raise HeavyError("registry supervisor identity is invalid")
        recorded_boot = supervisor.get("boot_id")
        if not isinstance(recorded_boot, str) or not re.fullmatch(
            r"[1-9][0-9]*", recorded_boot
        ):
            raise HeavyError("registry boot identity is invalid")
        if recorded_boot != boot_id:
            registry.remove(record["job_id"])
            continue
        if int(record.get("created_ns", 0)) >= snapshot_started_ns:
            continue
        alive, supervisor_alive = _record_live(record, table)
        if not alive and not supervisor_alive:
            registry.remove(record["job_id"])


@dataclass
class SupervisorDeps:
    """Injectable collaborators for the supervisor, defaulting to live system calls."""

    sample: Callable[[], Sample] = lambda: sample_with_emergency()
    clock: Callable[[], float] = monotonic
    monotonic_ns: Callable[[], int] = monotonic_ns
    sleep: Callable[[float], None] = time.sleep
    process_table_reader: Callable[[], Dict[int, ProcessInfo]] = process_table
    boot_reader: Callable[[], str] = kernel_boot_identity
    legacy_slots: Callable[[Dict[int, ProcessInfo]], int] = legacy_slot_count
    launch_gated_workload: Optional[
        Callable[[Sequence[str]], Tuple[Any, Callable[[], None], Callable[[], None]]]
    ] = None
    launch_watchdog: Optional[Callable[[str], Any]] = None
    terminate: Callable[..., bool] = terminate_owned_group
    signal_group: Callable[[int, int], None] = os.killpg
    getpgid: Callable[[int], int] = os.getpgid
    getsid: Callable[[int], int] = os.getsid
    wall_clock: Callable[[], float] = time.time


def _queue_sort_key(record: Dict[str, Any], now_ns: Optional[int] = None) -> Tuple[int, int, str]:
    created = int(record.get("created_ns", 0))
    now = monotonic_ns() if now_ns is None else now_ns
    role = record.get("role")
    priority = 0 if now - created > 600_000_000_000 else (
        1 if role == "deploy" else 2 if role == "review" else 3
    )
    return (priority, created, str(record.get("queue_id", "")))


def _prune_queue_records_locked(
    registry: Registry,
    table: Dict[int, ProcessInfo],
    boot_id: str,
) -> List[Dict[str, Any]]:
    for queued in registry.queue_records():
        identity = queued["process"]
        if queued.get("boot_id") != boot_id or not _identity_matches(
            table.get(identity.get("pid")), identity
        ):
            registry.remove_queue(queued["queue_id"])
    return registry.queue_records()


def _enqueue_job(
    registry: Registry,
    *,
    task_key: str,
    task_id: str,
    command_basename: str,
    role: str,
    deps: SupervisorDeps,
) -> str:
    boot_id = deps.boot_reader()
    table = deps.process_table_reader()
    process = _supervisor_identity(task_key, boot_id, table, os.getuid())
    queue_id = uuid.uuid4().hex
    queued = {
        "schema": 1,
        "kind": "queue",
        "queue_id": queue_id,
        "uid": os.getuid(),
        "task_key": task_key,
        "task_id": task_id,
        "command_basename": command_basename,
        "role": role,
        "created_ns": deps.monotonic_ns(),
        "boot_id": boot_id,
        "process": process,
    }
    with registry.lock():
        rows = _prune_queue_records_locked(registry, table, boot_id)
        registry.create_queue(queued)
        rows.append(queued)
        rows.sort(key=lambda row: _queue_sort_key(row, deps.monotonic_ns()))
        position = next(
            index + 1 for index, row in enumerate(rows) if row["queue_id"] == queue_id
        )
    _log_event(
        registry.directory,
        "queued",
        queued,
        detail="priority position {}".format(position),
    )
    print("heavy: queued role={} position={}".format(role, position), file=sys.stderr)
    return queue_id


def critical_pressure(sample: Sample, *, load_proxy: bool = True) -> bool:
    """Return True when a sample meets any critical pressure threshold.

    load_proxy=False ignores the load-average stand-in for a missing CPU reading.
    """
    return (
        sample.pressure_level == CRITICAL_PRESSURE_LEVEL
        or (
            _finite_nonnegative(sample.memory_used_pct)
            and sample.memory_used_pct >= MAX_MEMORY_PCT
        )
        or (
            load_proxy
            and not _finite_nonnegative(sample.cpu_busy_pct)
            and _finite_nonnegative(sample.load_per_core)
            and sample.load_per_core >= CRITICAL_LOAD_PER_CORE
        )
    )


def _host_reason(
    sample: Sample, load_high_count: int = 0, paused: bool = False
) -> Optional[str]:
    if sample.pressure_level == CRITICAL_PRESSURE_LEVEL:
        return "critical-pressure"
    if sample.cpu_busy_pct >= MAX_CPU_PCT:
        return "cpu-threshold"
    if sample.memory_used_pct >= MAX_MEMORY_PCT:
        return "memory-threshold"
    if memory_load_block_reason(
        pressure=sample.pressure_level,
        free_percent=sample.free_percent,
        swap_growth=sample.swap_growth_bytes_per_second,
        swapout_rate=sample.swapout_bytes_per_second,
        headroom=sample.headroom_bytes,
        physical=sample.physical_bytes,
        headroom_fraction=(
            HEADROOM_FRACTION if paused else PAUSE_HEADROOM_FRACTION
        ),
    ) in ("memory-pressure-warning-low-free", "swap-growth", "memory-headroom"):
        return "memory-headroom-or-swap-pressure"
    return None


def _role_slot_available(
    role: str,
    active: List[Dict[str, Any]],
    queues: List[Dict[str, Any]],
    slot_limit: int,
    legacy_count: int = 0,
) -> bool:
    """Keep one slot for review/deploy demand without changing global capacity."""
    if role in ("review", "deploy"):
        return True
    priority_demand = any(
        row.get("role") in ("review", "deploy") for row in active + queues
    )
    ordinary_count = legacy_count + sum(
        row.get("role", "ordinary") not in ("review", "deploy") for row in active
    )
    return not priority_demand or ordinary_count < max(0, slot_limit - 1)


def _reserve_job(
    registry: Registry,
    task_key: str,
    task_id: str,
    command_basename: str,
    sample: Sample,
    deps: SupervisorDeps,
    *,
    queue_id: Optional[str] = None,
    role: str = "ordinary",
    max_runtime_seconds: Optional[float] = None,
) -> Tuple[Optional[str], Optional[str]]:
    ephemeral_queue = queue_id is None
    snapshot_started_ns = deps.monotonic_ns()
    boot_id = deps.boot_reader()
    table = deps.process_table_reader()
    legacy_count = deps.legacy_slots(table)
    supervisor = _supervisor_identity(task_key, boot_id, table, os.getuid())
    with registry.lock():
        if _legacy_draining(registry):
            return None, "legacy-draining"
        if os.path.lexists(str(registry.directory / ".activation-pending")):
            return None, "installation-awaits-legacy-drain"
        records = registry.records()
        _prune_finished_locked(registry, records, table, snapshot_started_ns, boot_id)
        records = registry.records()
        queues = _prune_queue_records_locked(registry, table, boot_id)
        if queue_id is None:
            queue_id = uuid.uuid4().hex
            queued = {
                "schema": 1,
                "kind": "queue",
                "queue_id": queue_id,
                "uid": os.getuid(),
                "task_key": task_key,
                "task_id": task_id,
                "command_basename": command_basename,
                "role": role,
                "created_ns": deps.monotonic_ns(),
                "boot_id": boot_id,
                "process": supervisor,
            }
            registry.create_queue(queued)
            queues.append(queued)
        current_queue = next(
            (row for row in queues if row.get("queue_id") == queue_id), None
        )
        if (
            current_queue is None
            or current_queue.get("task_key") != task_key
            or current_queue.get("role") != role
            or not _identity_matches(
                table.get(supervisor["pid"]), current_queue.get("process", {})
            )
        ):
            if ephemeral_queue:
                registry.remove_queue(queue_id)
            return None, "queue-identity-unavailable"
        queues.sort(key=lambda row: _queue_sort_key(row, snapshot_started_ns))
        active = [
            row for row in records if row.get("state") not in ("complete", "removed")
        ]
        try:
            slot_limit = _effective_slot_limit(
                registry, sample, now=deps.wall_clock(), boot_id=boot_id
            )
        except TelemetryError:
            if ephemeral_queue:
                registry.remove_queue(queue_id)
            return None, "capacity-unavailable"
        busy_tasks = {row.get("task_key") for row in active}
        deploy_active = any(row.get("role") == "deploy" for row in active)
        eligible_queues = [
            row for row in queues
            if row.get("task_key") not in busy_tasks
            and not (deploy_active and row.get("role") == "deploy")
            and _role_slot_available(
                row.get("role", "ordinary"), active, queues, slot_limit, legacy_count
            )
        ]
        if task_key in busy_tasks:
            if ephemeral_queue:
                registry.remove_queue(queue_id)
            return None, "task-slot-busy"
        if not eligible_queues or eligible_queues[0].get("queue_id") != queue_id:
            if ephemeral_queue:
                registry.remove_queue(queue_id)
            return None, "reviewer-priority" if eligible_queues and eligible_queues[
                0
            ].get("role") == "review" else "queue-order"
        active = [
            row for row in records if row.get("state") not in ("complete", "removed")
        ]
        same_task = any(row.get("task_key") == task_key for row in active)
        reason = admission_block_reason(
            sample,
            now=deps.clock(),
            active_count=len(active) + legacy_count,
            task_already_active=same_task,
            slot_limit=slot_limit,
        )
        if reason:
            if ephemeral_queue:
                registry.remove_queue(queue_id)
            return None, reason
        job_id = uuid.uuid4().hex
        record = {
            "schema": 1,
            "clock": "CLOCK_MONOTONIC",
            "job_id": job_id,
            "uid": os.getuid(),
            "task_key": task_key,
            "task_id": task_id,
            "command_basename": command_basename,
            "role": role,
            "created_ns": deps.monotonic_ns(),
            "state": "starting",
            "supervisor": supervisor,
            "workload": None,
            "curtail_request": None,
            "termination": None,
            "max_runtime_seconds": max_runtime_seconds,
        }
        registry.create(record)
        registry.write_heartbeat(job_id, deps.monotonic_ns())
        if current_queue is not None:
            resume_queue_agent_pause(current_queue, deps)
            try:

                def clear_agent_pause(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                    if not row.get("agent_pause"):
                        return None
                    updated = dict(row)
                    updated.pop("agent_pause", None)
                    return updated

                registry.update_queue(queue_id, clear_agent_pause)
            except Exception:
                pass
        registry.remove_queue(queue_id)
        return job_id, None


def _update_workload(
    registry: Registry, job_id: str, workload: Dict[str, Any], started_ns: int
) -> Dict[str, Any]:
    with registry.lock():

        def change(record: Dict[str, Any]) -> Dict[str, Any]:
            record["workload"] = workload
            record["workload_started_ns"] = started_ns
            record["state"] = "running"
            return record

        updated = registry.update(job_id, change)
        if updated is None:
            raise HeavyError("workload registry entry disappeared")
        return updated


def _default_launch_gated_workload(
    argv: Sequence[str],
) -> Tuple[subprocess.Popen, Callable[[], None], Callable[[], None]]:
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(
            [
                "/usr/bin/python3",
                "-I",
                os.path.realpath(__file__),
                "--workload-bootstrap",
                str(read_fd),
            ]
            + list(argv),
            start_new_session=True,
            close_fds=True,
            pass_fds=(read_fd,),
        )
    except Exception:
        os.close(read_fd)
        os.close(write_fd)
        raise
    os.close(read_fd)
    gate = {"fd": write_fd}

    def close_gate(open_child: bool) -> None:
        fd = gate.pop("fd", None)
        if fd is None:
            return
        try:
            if open_child:
                os.write(fd, b"1")
        except OSError:
            pass
        finally:
            os.close(fd)

    return process, lambda: close_gate(True), lambda: close_gate(False)


def _workload_bootstrap(read_fd: int, argv: Sequence[str]) -> int:
    try:
        with os.fdopen(read_fd, "rb") as gate:
            opened = gate.read(1) == b"1"
    except OSError:
        return 125
    if not opened or not argv:
        return 125
    try:
        os.execvp(argv[0], list(argv))
    except OSError:
        print("heavy: workload launch failed", file=sys.stderr)
        return 127


def _default_launch_watchdog(job_id: str) -> subprocess.Popen:
    helper_path = os.path.realpath(__file__)
    environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONNOUSERSITE": "1"}
    return subprocess.Popen(
        ["/usr/bin/python3", "-I", helper_path, "--watchdog", job_id],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
        env=environment,
    )


def _stop_watchdog(watchdog: Any) -> None:
    if watchdog is None:
        return
    try:
        if watchdog.poll() is None:
            watchdog.send_signal(signal.SIGTERM)
        watchdog.wait(timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if watchdog.poll() is None:
                watchdog.kill()
            watchdog.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _normal_completion(workload: Dict[str, Any], deps: SupervisorDeps) -> bool:
    members = _safe_group_members(
        workload,
        table_reader=deps.process_table_reader,
        getpgid=deps.getpgid,
        getsid=deps.getsid,
        boot_reader=deps.boot_reader,
    )
    return members == []


def _curtail_current(
    registry: Registry,
    job_id: str,
    workload: Dict[str, Any],
    reason: str,
    deps: SupervisorDeps,
    workload_process: Any = None,
) -> bool:
    claimed = _claim_termination(
        registry,
        job_id,
        reason,
        claimant_pid=os.getpid(),
        expected_workload=workload,
    )
    if claimed is None:
        return False
    try:
        current = _record(registry, job_id)
    except Exception:
        return False
    if (current.get("termination") or {}).get("claimant_pid") != os.getpid():
        return False
    try:
        success = deps.terminate(
            workload,
            reason=reason,
            signal_group=deps.signal_group,
            sleep=deps.sleep,
            table_reader=deps.process_table_reader,
            getpgid=deps.getpgid,
            getsid=deps.getsid,
            boot_reader=deps.boot_reader,
        )
    except Exception:
        success = False
    if workload_process is not None:
        try:
            workload_process.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            pass
    _log_event(
        registry.directory,
        "curtailed" if success else "curtail-identity-failed",
        claimed,
        detail=reason,
    )
    return success


def _sample_invalid_reason(sample: Sample, now: float) -> Optional[str]:
    if not isinstance(sample, Sample):
        return "telemetry-invalid"
    values = (
        sample.cpu_busy_pct,
        sample.memory_used_pct,
        sample.headroom_bytes,
        sample.physical_bytes,
        sample.load_per_core,
        sample.captured_monotonic,
        sample.free_percent,
        sample.swap_growth_bytes_per_second,
        sample.swapout_bytes_per_second,
    )
    if not all(_finite_nonnegative(value) for value in values):
        return "telemetry-missing"
    age = now - sample.captured_monotonic
    if age < 0 or age > SAMPLE_MAX_AGE:
        return "telemetry-stale"
    if sample.pressure_level not in (
        NORMAL_PRESSURE_LEVEL,
        WARNING_PRESSURE_LEVEL,
        CRITICAL_PRESSURE_LEVEL,
    ):
        return "telemetry-invalid"
    if (
        sample.physical_cores is None
        or isinstance(sample.physical_cores, bool)
        or not isinstance(sample.physical_cores, int)
        or sample.physical_cores <= 0
    ):
        return "telemetry-missing"
    if (
        sample.cpu_busy_pct > 100
        or sample.memory_used_pct > 100
        or sample.physical_bytes <= 0
        or sample.headroom_bytes > sample.physical_bytes
        or sample.free_percent > 100
    ):
        return "telemetry-invalid"
    return None


def _signal_owned_group(
    identity: Dict[str, Any], signum: int, deps: SupervisorDeps
) -> bool:
    if (
        identity.get("uid") != os.getuid()
        or not identity.get("task_key")
        or identity.get("pid") != identity.get("pgid")
        or not identity.get("boot_id")
    ):
        return False
    members = _safe_group_members(
        identity,
        table_reader=deps.process_table_reader,
        getpgid=deps.getpgid,
        getsid=deps.getsid,
        boot_reader=deps.boot_reader,
    )
    if not members:
        return False
    try:
        deps.signal_group(int(identity["pgid"]), signum)
    except (OSError, ValueError):
        return False
    return True


def _process_pause_identity(
    pid: int,
    task_key: str,
    boot_id: str,
    table: Dict[int, ProcessInfo],
    uid: int,
) -> Optional[Dict[str, Any]]:
    info = table.get(pid)
    if info is None or info.uid != uid:
        return None
    return {
        "pid": info.pid,
        "start": info.start_token,
        "uid": info.uid,
        "boot_id": boot_id,
        "task_key": task_key,
    }


def signal_verified_processes(
    identities: Sequence[Dict[str, Any]],
    signum: int,
    deps: SupervisorDeps,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Send a signal to each process whose identity still matches the live process table.

    Args:
        identities: Recorded process identities (pid, uid, start token, task key, boot id).
        signum: Signal number to send.
        deps: Supervisor dependencies providing the process table reader.

    Returns:
        A tuple of identities that were signalled and identities that were not.

    """
    try:
        table = deps.process_table_reader()
    except Exception:
        return [], [item for item in identities if isinstance(item, dict)]
    succeeded: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for identity in identities:
        if not isinstance(identity, dict):
            continue
        if (
            identity.get("uid") != os.getuid()
            or not identity.get("task_key")
            or not identity.get("boot_id")
            or type(identity.get("pid")) is not int
        ):
            failed.append(identity)
            continue
        if not _identity_matches(table.get(identity["pid"]), identity):
            failed.append(identity)
            continue
        try:
            os.kill(int(identity["pid"]), signum)
        except OSError:
            failed.append(identity)
            continue
        succeeded.append(identity)
    return succeeded, failed


def resume_queue_agent_pause(
    record: Dict[str, Any], deps: SupervisorDeps
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Send SIGCONT to the agent processes paused for a queued job.

    Args:
        record: Registry record that may hold an ``agent_pause`` entry.
        deps: Supervisor dependencies providing the process table reader.

    Returns:
        A tuple of whether every process resumed and the identities that failed to resume.

    """
    pause = record.get("agent_pause") or {}
    if pause.get("status") not in ("paused", "pause-pending", "requested"):
        return True, []
    processes = pause.get("processes")
    if not isinstance(processes, list) or not processes:
        return True, []
    _ok, failed = signal_verified_processes(processes, signal.SIGCONT, deps)
    return not failed, failed


def _request_global_pause(
    registry: Registry, reason: str, deps: SupervisorDeps, *, urgent: bool = False
) -> Optional[str]:
    if urgent:
        requested = []
        with registry.lock():
            for current in registry.records():
                if (
                    current.get("state") != "running"
                    or not isinstance(_workload_identity(current), dict)
                    or current.get("termination")
                    or current.get("curtail_request")
                    or current.get("pause")
                ):
                    continue
                job_id = current["job_id"]

                def mark(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                    if record.get("state") != "running" or _workload_identity(
                        record
                    ) != _workload_identity(current):
                        return None
                    record["pause"] = {
                        "status": "requested",
                        "reason": reason,
                        "source": "global-pressure",
                        "requested_ns": deps.monotonic_ns(),
                        "selection": "critical-all",
                    }
                    record["state"] = "pause-requested"
                    return record

                changed = registry.update(job_id, mark)
                if changed is not None:
                    requested.append(changed)
        for record in requested:
            _log_event(
                registry.directory,
                "pause-requested",
                record,
                detail=reason + "; critical-all",
            )
        return requested[0]["job_id"] if requested else None
    changed = None
    with registry.lock():
        records = registry.records()
        if any(
            isinstance(record.get("pause"), dict)
            and record["pause"].get("status") == "requested"
            for record in records
        ):
            return None
        protocol = registry._read_record(PROTOCOL_RECORD_ID)
        boot_id = deps.boot_reader()
        now_ns = deps.monotonic_ns()
        last_request_ns = protocol.get("last_pause_request_ns")
        last_request_boot = protocol.get("last_pause_boot_id")
        if last_request_boot is not None and not isinstance(last_request_boot, str):
            return None
        if last_request_boot == boot_id:
            if (
                isinstance(last_request_ns, bool)
                or not isinstance(last_request_ns, int)
                or last_request_ns < 0
                or now_ns < last_request_ns
            ):
                return None
            if now_ns - last_request_ns < PAUSE_REQUEST_SPACING_NS:
                return None
        elif last_request_boot is None and last_request_ns is not None:
            return None
        running = [
            record
            for record in records
            if record.get("state") == "running"
            and isinstance(_workload_identity(record), dict)
            and not record.get("termination")
            and not record.get("curtail_request")
        ]
        ordinary = [
            record for record in running if record.get("role", "ordinary") != "review"
        ]
        candidates = ordinary or [
            record for record in running if record.get("role") == "review"
        ]
        if not candidates:
            return None
        target = max(candidates, key=lambda row: int(row.get("created_ns", 0)))
        job_id = target["job_id"]
        selection = "ordinary-before-review" if ordinary else "review-fallback"

        def record_pause_slot(current: Dict[str, Any]) -> Dict[str, Any]:
            current["last_pause_request_ns"] = now_ns
            current["last_pause_boot_id"] = boot_id
            current["last_pause_job_id"] = job_id
            current["last_pause_selection"] = selection
            return current

        registry.update(PROTOCOL_RECORD_ID, record_pause_slot)

        def request(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            if (
                record.get("state") != "running"
                or _workload_identity(record) != _workload_identity(target)
                or record.get("termination")
                or record.get("curtail_request")
                or record.get("pause")
            ):
                return None
            record["pause"] = {
                "status": "requested",
                "reason": reason,
                "source": "global-pressure",
                "requested_ns": deps.monotonic_ns(),
                "selection": selection,
            }
            record["state"] = "pause-requested"
            return record

        changed = registry.update(job_id, request)
    if changed is None:
        return None
    _log_event(
        registry.directory, "pause-requested", changed, detail=reason + "; " + selection
    )
    print(
        "heavy: pause requested task={} role={} reason={}".format(
            changed.get("task_id"),
            changed.get("role", "ordinary"),
            reason + "; " + selection,
        ),
        file=sys.stderr,
    )
    return changed["job_id"]


def request_critical_pauses() -> List[str]:
    """Request pauses for workloads under critical pressure and return their job ids."""
    registry = Registry(state_directory())
    registry.ensure_protocol()
    _request_global_pause(registry, "critical-pressure", SupervisorDeps(), urgent=True)
    with registry.lock(exclusive=False):
        return [
            record["job_id"]
            for record in registry.records()
            if (record.get("pause") or {}).get("reason") == "critical-pressure"
            and (record.get("pause") or {}).get("status") in ("requested", "paused")
        ]


def _apply_pause_request(
    registry: Registry, job_id: str, workload: Dict[str, Any], deps: SupervisorDeps
) -> bool:
    changed = None
    with registry.lock():
        current = registry._read_record(job_id)
        pause = current.get("pause") or {}
        if (
            pause.get("status") != "requested"
            or _workload_identity(current) != workload
            or current.get("termination")
            or current.get("curtail_request")
        ):
            return False
        if not _signal_owned_group(workload, signal.SIGSTOP, deps):
            return False

        def mark_paused(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            current_pause = record.get("pause") or {}
            if (
                _workload_identity(record) != workload
                or current_pause.get("status") != "requested"
                or current_pause.get("requested_ns") != pause.get("requested_ns")
                or record.get("termination")
                or record.get("curtail_request")
            ):
                return None
            current_pause["status"] = "paused"
            current_pause["paused_ns"] = deps.monotonic_ns()
            record["pause"] = current_pause
            record["state"] = "paused"
            return record

        changed = registry.update(job_id, mark_paused)
    if changed is None:
        return False
    try:
        _log_event(
            registry.directory,
            "paused",
            changed,
            detail=(changed.get("pause") or {}).get("reason"),
        )
    except Exception:
        pass
    return True


def _resume_current(
    registry: Registry,
    job_id: str,
    workload: Dict[str, Any],
    sample: Sample,
    deps: SupervisorDeps,
) -> bool:
    changed = None
    with registry.lock():
        current = registry._read_record(job_id)
        pause = current.get("pause") or {}
        if (
            pause.get("status") != "paused"
            or _workload_identity(current) != workload
            or current.get("termination")
            or current.get("curtail_request")
            or _legacy_draining(registry)
        ):
            return False
        try:
            boot_id = deps.boot_reader()
            slot_limit = _effective_slot_limit(
                registry,
                sample,
                now=deps.wall_clock(),
                boot_id=boot_id,
            )
        except Exception:
            return False
        if slot_limit <= 0:
            return False
        try:
            table = deps.process_table_reader()
            active_count = 0
            active_records = []
            for row in registry.records():
                if row.get("state") in ("paused", "complete", "removed"):
                    continue
                supervisor = row.get("supervisor")
                if (
                    not isinstance(supervisor, dict)
                    or supervisor.get("boot_id") != boot_id
                ):
                    continue
                active, supervisor_active = _record_live(row, table)
                if active or supervisor_active:
                    active_count += 1
                    active_records.append(row)
            legacy_count = deps.legacy_slots(table)
            active_count += legacy_count
            queues = _prune_queue_records_locked(registry, table, boot_id)
            if not _role_slot_available(
                current.get("role", "ordinary"), active_records, queues,
                slot_limit, legacy_count,
            ):
                return False
        except Exception:
            return False
        if active_count >= slot_limit or not _signal_owned_group(
            workload, signal.SIGCONT, deps
        ):
            return False

        def mark_running(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            if (
                _workload_identity(record) != workload
                or (record.get("pause") or {}).get("status") != "paused"
                or record.get("termination")
                or record.get("curtail_request")
            ):
                return None
            record.pop("pause", None)
            record["state"] = "running"
            return record

        changed = registry.update(job_id, mark_running)
    if changed is None:
        return False
    try:
        _log_event(
            registry.directory,
            "resumed",
            changed,
            detail="healthy telemetry and positive capacity",
        )
    except Exception:
        pass
    return True


def _runtime_ceiling_from_environment() -> float:
    raw = os.environ.get(RUNTIME_LIMIT_ENV, "").strip()
    if not raw:
        return float(MAX_RUNTIME_SECONDS)
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        raise HeavyError(RUNTIME_LIMIT_ENV + " must be a positive number of seconds")
    return min(value, float(MAX_RUNTIME_SECONDS))


def _record_ceiling(record: Dict[str, Any]) -> float:
    return float(record.get("max_runtime_seconds") or MAX_RUNTIME_SECONDS)


def _format_duration(seconds: float) -> str:
    whole = int(seconds)
    if whole == seconds and whole % 60 == 0:
        return str(whole // 60) + "m"
    return "{:g}s".format(seconds)


def _limit_notice(record: Dict[str, Any]) -> Optional[str]:
    if (record.get("termination") or {}).get("reason") != WALL_CLOCK_REASON:
        return None
    return "terminated: {} {}".format(
        WALL_CLOCK_REASON, _format_duration(_record_ceiling(record))
    )


def _pid_alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, TypeError, ValueError):
        return True
    return True


def _limit_action(
    record: Dict[str, Any],
    now_ns: int,
    boot_reader: Callable[[], str],
) -> Optional[bool]:
    """Return None when the job is within its ceiling, else whether to take over an earlier claim."""
    workload = _workload_identity(record)
    if workload is None or record.get("state") in ("starting", "complete", "removed"):
        return None
    started_ns = int(record.get("workload_started_ns") or record.get("created_ns") or now_ns)
    if now_ns - started_ns < int(_record_ceiling(record) * 1_000_000_000):
        return None
    if workload.get("boot_id") != boot_reader():
        return None
    termination = record.get("termination")
    if not termination:
        return False
    claimed_ns = int(termination.get("takeover_ns") or termination.get("requested_ns") or 0)
    if termination.get("reason") == WALL_CLOCK_REASON and (
        now_ns - claimed_ns >= LIMIT_RETRY_NS
        or not _pid_alive(termination.get("claimant_pid"))
    ):
        return True
    return None


def _limit_claim_active(record: Dict[str, Any], now_ns: int) -> bool:
    termination = record.get("termination") or {}
    claimed_ns = int(termination.get("takeover_ns") or termination.get("requested_ns") or 0)
    return (
        termination.get("reason") == WALL_CLOCK_REASON
        and now_ns - claimed_ns < LIMIT_RETRY_NS
        and _pid_alive(termination.get("claimant_pid"))
    )


def _terminate_for_limit(
    registry: Registry,
    record: Dict[str, Any],
    *,
    takeover: bool,
    terminate: Callable[..., bool],
    table_reader: Callable[[], Dict[int, ProcessInfo]],
    boot_reader: Callable[[], str],
) -> bool:
    workload = _workload_identity(record)
    claimed = _claim_termination(
        registry,
        record["job_id"],
        WALL_CLOCK_REASON,
        claimant_pid=os.getpid(),
        expected_workload=workload,
        takeover=takeover,
        observed_termination=record.get("termination") if takeover else None,
    )
    if claimed is None:
        return False
    success = terminate(
        workload,
        reason=WALL_CLOCK_REASON,
        table_reader=table_reader,
        boot_reader=boot_reader,
    )
    _log_event(
        registry.directory,
        "limit-terminated" if success else "limit-terminate-failed",
        claimed,
        detail=WALL_CLOCK_REASON,
    )
    if success:
        try:
            _mark_complete(registry, record["job_id"])
        except (OSError, HeavyError):
            pass
    return success


def enforce_runtime_limits(
    registry: Registry, deps: Optional[SupervisorDeps] = None
) -> List[str]:
    """Terminate every job past the wall-clock ceiling and return their job ids."""
    dependencies = deps or SupervisorDeps()
    with registry.lock(exclusive=False):
        job_ids = registry._job_ids()
    now_ns = dependencies.monotonic_ns()
    terminated = []
    for job_id in job_ids:
        try:
            if job_id == PROTOCOL_RECORD_ID:
                continue
            record = _record(registry, job_id)
            takeover = _limit_action(record, now_ns, dependencies.boot_reader)
            if takeover is None:
                continue
            if _terminate_for_limit(
                registry,
                record,
                takeover=takeover,
                terminate=dependencies.terminate,
                table_reader=dependencies.process_table_reader,
                boot_reader=dependencies.boot_reader,
            ):
                terminated.append(job_id)
        except Exception:
            continue
    return terminated


def _reap_over_limit(registry: Registry, deps: Optional[SupervisorDeps] = None) -> None:
    try:
        enforce_runtime_limits(registry, deps)
    except Exception:
        pass


def _supervise_running(
    registry: Registry,
    job_id: str,
    record: Dict[str, Any],
    workload_process: Any,
    watchdog: Any,
    deps: SupervisorDeps,
    *,
    stop_event: Callable[[], bool] = lambda: False,
) -> int:
    workload = _workload_identity(record)
    if workload is None:
        raise HeavyError("workload identity missing")
    pressure_since: Optional[float] = None
    healthy_since: Optional[float] = None
    last_pause_retry: Optional[float] = None
    last_resume_retry: Optional[float] = None
    root_exit_code: Optional[int] = None
    while True:
        if watchdog is not None and watchdog.poll() is not None:
            if _normal_completion(workload, deps):
                notice = _limit_notice(_record(registry, job_id))
                if notice:
                    print("heavy: " + notice, file=sys.stderr)
                    return LIMIT_EXIT_CODE
            _curtail_current(
                registry, job_id, workload, "watchdog-failure", deps, workload_process
            )
            return 125
        if stop_event():
            _curtail_current(
                registry, job_id, workload, "interrupted", deps, workload_process
            )
            return 130
        deadline = deps.clock() + SAMPLE_INTERVAL
        registry.write_heartbeat(job_id, deps.monotonic_ns())
        if root_exit_code is None:
            root_exit_code = workload_process.poll()
        if root_exit_code is not None and _normal_completion(workload, deps):
            notice = _limit_notice(_record(registry, job_id))
            if notice:
                print("heavy: " + notice, file=sys.stderr)
                return LIMIT_EXIT_CODE
            return int(root_exit_code)
        current = _record(registry, job_id)
        request = current.get("curtail_request") or {}
        if request.get("source") == "external-request" or (
            request and request.get("source") != "host-alarm"
        ):
            _curtail_current(
                registry,
                job_id,
                workload,
                request.get("reason", "requested"),
                deps,
                workload_process,
            )
            return 125
        if request.get("source") == "host-alarm":
            _clear_curtail_request(registry, job_id)
        sample = None
        sample_error = False
        try:
            sample = deps.sample()
        except Exception as exc:
            sample = getattr(exc, "partial_sample", None)
            sample_error = True
        now = deps.clock()
        invalid_reason = (
            "telemetry-missing"
            if sample_error or sample is None
            else _sample_invalid_reason(sample, now)
        )
        slot_limit = None
        pressure_reason = None
        resume_blocked = False
        if invalid_reason is None and sample is not None:
            try:
                slot_limit = _effective_slot_limit(
                    registry,
                    sample,
                    now=deps.wall_clock(),
                    boot_id=deps.boot_reader(),
                )
                pressure_reason = _host_reason(sample)
                resume_blocked = (
                    pressure_reason is None
                    and _host_reason(sample, paused=True) is not None
                )
            except Exception:
                invalid_reason = "capacity-unavailable"
        critical = sample is not None and critical_pressure(sample)
        unhealthy_reason = (
            "critical-pressure" if critical else (invalid_reason or pressure_reason)
        )
        if unhealthy_reason:
            healthy_since = None
            if pressure_since is None:
                pressure_since = now
            if critical or now - pressure_since >= PRESSURE_HOLD_SECONDS:
                try:
                    _request_global_pause(
                        registry, unhealthy_reason, deps, urgent=critical
                    )
                except Exception:
                    pass
        else:
            pressure_since = None
            current = _record(registry, job_id)
            if (
                (current.get("pause") or {}).get("status") == "paused"
                and sample is not None
                and slot_limit is not None
                and slot_limit > 0
                and not resume_blocked
            ):
                if healthy_since is None:
                    healthy_since = now
                elif now - healthy_since >= RECOVERY_HOLD_SECONDS:
                    try:
                        resumed = _resume_current(
                            registry, job_id, workload, sample, deps
                        )
                    except Exception:
                        resumed = False
                    if resumed:
                        healthy_since = None
                        last_resume_retry = None
                    elif last_resume_retry is None or now - last_resume_retry >= 30.0:
                        try:
                            _log_event(
                                registry.directory,
                                "resume-retry",
                                current,
                                detail="capacity, active slots, identity, or signal not confirmed",
                            )
                        except Exception:
                            pass
                        last_resume_retry = now
            else:
                healthy_since = None
        current = _record(registry, job_id)
        if (current.get("pause") or {}).get("status") == "requested":
            try:
                paused = _apply_pause_request(registry, job_id, workload, deps)
            except Exception:
                paused = False
            if paused:
                last_pause_retry = None
            elif last_pause_retry is None or now - last_pause_retry >= 30.0:
                try:
                    _log_event(
                        registry.directory,
                        "pause-retry",
                        current,
                        detail="identity or signal not confirmed",
                    )
                except Exception:
                    pass
                last_pause_retry = now
        deps.sleep(max(0.0, deadline - deps.clock()))


def _launch_job(
    argv: Sequence[str],
    *,
    task_key: str,
    task_id: str,
    command_basename: str,
    registry: Registry,
    deps: SupervisorDeps,
    role: str = "ordinary",
    project_key: Optional[str] = None,
    stop_event: Callable[[], bool] = lambda: False,
) -> int:
    started = deps.clock()
    last_message = 0.0
    job_id = None
    max_runtime_seconds = _runtime_ceiling_from_environment()
    queue_id = _enqueue_job(
        registry,
        task_key=task_key,
        task_id=task_id,
        command_basename=command_basename,
        role=role,
        deps=deps,
    )
    reserved = False
    try:
        while job_id is None:
            if stop_event():
                return 130
            _reap_over_limit(registry, deps)
            next_sample = deps.clock() + SAMPLE_INTERVAL
            try:
                sample = deps.sample()
            except Exception as exc:
                if deps.clock() - started >= MAX_WAIT_SECONDS:
                    raise HeavyError(
                        "admission timed out: telemetry unavailable"
                    ) from exc
                if deps.clock() - last_message >= 60:
                    print("heavy: waiting (telemetry unavailable)", file=sys.stderr)
                    last_message = deps.clock()
                deps.sleep(max(0.0, next_sample - deps.clock()))
                continue
            try:
                job_id, reason = _reserve_job(
                    registry,
                    task_key,
                    task_id,
                    command_basename,
                    sample,
                    deps,
                    queue_id=queue_id,
                    role=role,
                    max_runtime_seconds=max_runtime_seconds,
                )
            except Exception as exc:
                raise HeavyError("cannot safely reserve a heavy job") from exc
            if job_id is not None:
                reserved = True
                break
            if deps.clock() - started >= MAX_WAIT_SECONDS:
                raise HeavyError("admission timed out: " + str(reason))
            if deps.clock() - last_message >= 60:
                print("heavy: waiting (" + str(reason) + ")", file=sys.stderr)
                last_message = deps.clock()
            deps.sleep(max(0.0, next_sample - deps.clock()))
    finally:
        if not reserved:
            with registry.lock():
                registry.remove_queue(queue_id)
    record: Dict[str, Any] = {}
    workload_process = None
    watchdog = None
    open_gate = None
    close_gate = None
    gate_opened = False
    cleanup_record = False
    project_fd = None
    try:
        record = _record(registry, job_id)
        project_fd = _acquire_project_lock(
            registry,
            project_key,
            clock=deps.clock,
            sleep=deps.sleep,
            stop_event=stop_event,
            heartbeat=lambda: registry.write_heartbeat(job_id, deps.monotonic_ns()),
        )
        launch = deps.launch_gated_workload or _default_launch_gated_workload
        workload_process, open_gate, close_gate = launch(argv)
        table = deps.process_table_reader()
        boot_id = record["supervisor"]["boot_id"]
        workload = _workload_identity_from_process(
            workload_process.pid,
            task_key,
            boot_id,
            table,
            getpgid=deps.getpgid,
            getsid=deps.getsid,
        )
        record = _update_workload(
            registry, job_id, workload, deps.monotonic_ns()
        )
        registry.write_heartbeat(job_id, deps.monotonic_ns())
        watchdog_launch = deps.launch_watchdog or _default_launch_watchdog
        watchdog = watchdog_launch(job_id)
        open_gate()
        gate_opened = True
        _log_event(registry.directory, "started", record)
        exit_code = _supervise_running(
            registry,
            job_id,
            record,
            workload_process,
            watchdog,
            deps,
            stop_event=stop_event,
        )
        cleanup_record = _normal_completion(workload, deps)
        _mark_complete(
            registry,
            job_id,
            state=("complete" if exit_code == 0 else "curtailed")
            if cleanup_record
            else "supervision-failed",
        )
        return exit_code
    except Exception:
        if close_gate is not None and not gate_opened:
            close_gate()
        if workload_process is not None and record.get("workload"):
            _curtail_current(
                registry,
                job_id,
                record["workload"],
                "supervisor-failure",
                deps,
                workload_process,
            )
            cleanup_record = _normal_completion(record["workload"], deps)
        elif workload_process is not None:
            try:
                workload_process.wait(timeout=2.0)
                cleanup_record = True
            except (OSError, subprocess.TimeoutExpired):
                try:
                    workload_process.kill()
                    workload_process.wait(timeout=1.0)
                    cleanup_record = True
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_record = False
        elif job_id:
            cleanup_record = True
        raise
    finally:
        try:
            if close_gate is not None and not gate_opened:
                try:
                    close_gate()
                except Exception:
                    pass
            try:
                if cleanup_record:
                    _mark_complete(registry, job_id, state="complete")
                else:
                    _mark_complete(registry, job_id, state="supervision-failed")
            except Exception:
                pass
            if cleanup_record:
                try:
                    _stop_watchdog(watchdog)
                except Exception:
                    pass
                try:
                    with registry.lock():
                        registry.remove(job_id)
                except Exception:
                    pass
            elif record.get("workload") and (
                watchdog is None or watchdog.poll() is not None
            ):
                try:
                    watchdog_launch = deps.launch_watchdog or _default_launch_watchdog
                    watchdog_launch(job_id)
                except Exception:
                    pass
        finally:
            if project_fd is not None:
                try:
                    fcntl.flock(project_fd, fcntl.LOCK_UN)
                finally:
                    os.close(project_fd)


def watchdog_loop(
    job_id: str,
    registry: Registry,
    *,
    clock_ns: Callable[[], int] = monotonic_ns,
    sleep: Callable[[float], None] = time.sleep,
    table_reader: Callable[[], Dict[int, ProcessInfo]] = process_table,
    boot_reader: Callable[[], str] = kernel_boot_identity,
    terminate: Callable[..., bool] = terminate_owned_group,
) -> int:
    """Watch a job's registry record and heartbeat, terminating its workload when they fail."""
    cached = None
    while True:
        try:
            record = _record(registry, job_id)
            heartbeat = registry.read_heartbeat(job_id)
        except Exception:
            if cached is None:
                return 1
            if os.path.isdir(str(registry.directory / job_id)):
                sleep(WATCHDOG_INTERVAL)
                continue
            try:
                if terminate(
                    cached["workload"],
                    reason="watchdog-registry-failure",
                    table_reader=table_reader,
                    boot_reader=boot_reader,
                ):
                    return 1
            except Exception:
                pass
            sleep(WATCHDOG_INTERVAL)
            continue
        if cached is None:
            cached = {
                "task_key": record.get("task_key"),
                "uid": record.get("uid"),
                "supervisor": record.get("supervisor"),
                "workload": record.get("workload"),
            }
            workload = cached["workload"]
            supervisor = cached["supervisor"]
            if (
                not workload
                or cached["uid"] != os.getuid()
                or workload.get("uid") != os.getuid()
                or workload.get("task_key") != cached["task_key"]
                or workload.get("boot_id") != supervisor.get("boot_id")
            ):
                return 1
        if (
            record.get("task_key") != cached["task_key"]
            or record.get("uid") != cached["uid"]
            or record.get("supervisor") != cached["supervisor"]
            or record.get("workload") != cached["workload"]
        ):
            try:
                success = terminate(
                    cached["workload"],
                    reason="watchdog-registry-identity-changed",
                    table_reader=table_reader,
                    boot_reader=boot_reader,
                )
            except Exception:
                success = False
            if success:
                return 1
            sleep(WATCHDOG_INTERVAL)
            continue
        if record.get("state") == "complete":
            try:
                members = _safe_group_members(
                    cached["workload"],
                    table_reader=table_reader,
                    boot_reader=boot_reader,
                )
            except Exception:
                members = None
            if members == []:
                return 0
        try:
            takeover = _limit_action(record, clock_ns(), boot_reader)
            if takeover is not None:
                _terminate_for_limit(
                    registry,
                    record,
                    takeover=takeover,
                    terminate=terminate,
                    table_reader=table_reader,
                    boot_reader=boot_reader,
                )
                sleep(WATCHDOG_INTERVAL)
                continue
        except Exception:
            pass
        if _limit_claim_active(record, clock_ns()):
            sleep(WATCHDOG_INTERVAL)
            continue
        heartbeat_age = clock_ns() - (heartbeat or 0)
        stale = heartbeat is None or heartbeat_age > int(
            WATCHDOG_STALE_SECONDS * 1_000_000_000
        )
        termination = record.get("termination") or {}
        if termination and not stale:
            sleep(WATCHDOG_INTERVAL)
            continue
        if stale:
            try:
                claimed = _claim_termination(
                    registry,
                    job_id,
                    "stale-supervision-heartbeat",
                    claimant_pid=os.getpid(),
                    expected_workload=cached["workload"],
                    takeover=bool(termination),
                    observed_termination=termination or None,
                )
            except Exception:
                claimed = None
            if claimed is None:
                try:
                    claimed = _takeover_termination(
                        registry,
                        job_id,
                        cached["workload"],
                        os.getpid(),
                        termination,
                    )
                except Exception:
                    claimed = None
            if claimed is None:
                try:
                    latest = _record(registry, job_id)
                except Exception:
                    sleep(WATCHDOG_INTERVAL)
                    continue
                if latest.get("termination") != (termination or None) or (
                    _limit_claim_active(latest, clock_ns())
                ):
                    sleep(WATCHDOG_INTERVAL)
                    continue
                try:
                    success = terminate(
                        cached["workload"],
                        reason="watchdog-claim-failure",
                        table_reader=table_reader,
                        boot_reader=boot_reader,
                    )
                except Exception:
                    success = False
                if success:
                    return 1
                sleep(WATCHDOG_INTERVAL)
                continue
            try:
                success = terminate(
                    cached["workload"],
                    reason="stale-supervision-heartbeat",
                    table_reader=table_reader,
                    boot_reader=boot_reader,
                )
            except Exception:
                success = False
            if success:
                try:
                    _mark_complete(registry, job_id, state="curtailed")
                except Exception:
                    pass
                return 0
        sleep(WATCHDOG_INTERVAL)


def _watchdog_takeover_record(
    record: Dict[str, Any],
    workload: Dict[str, Any],
    claimant_pid: int,
    observed: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if _workload_identity(record) != workload or not record.get("termination"):
        return None
    termination = record["termination"]
    if any(
        termination.get(key) != observed.get(key)
        for key in ("claimant_pid", "requested_ns", "takeover_ns")
    ):
        return None
    termination["claimant_pid"] = claimant_pid
    termination["takeover_ns"] = monotonic_ns()
    record["termination"] = termination
    record["state"] = "terminating"
    return record


def _takeover_termination(
    registry: Registry,
    job_id: str,
    workload: Dict[str, Any],
    claimant_pid: int,
    observed: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    with registry.lock():
        return registry.update(
            job_id,
            lambda current: _watchdog_takeover_record(
                current, workload, claimant_pid, observed
            ),
        )


def _watchdog_main(job_id: str) -> int:
    return watchdog_loop(job_id, Registry(state_directory()))


def _project_build_args(
    argv: Sequence[str], cwd: str
) -> Tuple[List[str], Optional[str]]:
    if not argv or os.path.basename(argv[0]) != "xcodebuild":
        return list(argv), None
    project_path = None
    for index, arg in enumerate(argv):
        if arg in ("-project", "-workspace") and index + 1 < len(argv):
            project_path = argv[index + 1]
            break
    base = Path(project_path).stem if project_path else Path(cwd).name
    project_key = base.lower() or hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]
    rewritten = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "-derivedDataPath":
            index += 2
            continue
        if arg.startswith("-derivedDataPath="):
            index += 1
            continue
        rewritten.append(arg)
        index += 1
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    derived_data = (
        home
        / "Library"
        / "Developer"
        / "Xcode"
        / "DerivedData"
        / ("shared-" + project_key)
    )
    rewritten.extend(["-derivedDataPath", str(derived_data)])
    return rewritten, project_key


def _acquire_project_lock(
    registry: Registry,
    project_key: Optional[str],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    stop_event: Callable[[], bool],
    heartbeat: Optional[Callable[[], None]] = None,
) -> Optional[int]:
    if project_key is None:
        return None
    digest = hashlib.sha256(project_key.encode("utf-8")).hexdigest()[:24]
    path = registry.directory / ("project-" + digest + ".lock")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != registry.uid
        or info.st_mode & 0o077
    ):
        os.close(fd)
        raise HeavyError("project lock file is unsafe")
    started = clock()
    try:
        while True:
            if heartbeat is not None:
                heartbeat()
            if stop_event():
                raise HeavyError("interrupted while waiting for project lock")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if clock() - started >= MAX_WAIT_SECONDS:
                    raise HeavyError("timed out waiting for xcodebuild project lock")
                sleep(min(SAMPLE_INTERVAL, 5.0))
    except Exception:
        os.close(fd)
        raise


def run_supervisor(
    argv: Sequence[str],
    *,
    registry: Optional[Registry] = None,
    task_key: Optional[str] = None,
    task_id: Optional[str] = None,
    deps: Optional[SupervisorDeps] = None,
    role: str = "ordinary",
    stop_event: Callable[[], bool] = lambda: False,
) -> int:
    """Queue or launch argv as a supervised workload and return its exit code."""
    if not argv or not str(argv[0]).strip():
        raise HeavyError("usage: heavy <command> [args...]")
    dependencies = deps or SupervisorDeps()
    reg = registry or Registry(state_directory())
    reg.ensure_protocol()
    if task_key is None or task_id is None:
        inferred_key, inferred_id = _task_identity()
        task_key = task_key or inferred_key
        task_id = task_id or inferred_id
    command, project_key = _project_build_args(argv, os.getcwd())
    command_basename = os.path.basename(command[0])
    if command_basename == "xcodebuild" and role != "review":
        taskpolicy = "/usr/sbin/taskpolicy"
        if not os.path.isfile(taskpolicy) or not os.access(taskpolicy, os.X_OK):
            raise HeavyError("taskpolicy is required for ordinary xcodebuild jobs")
        command = [taskpolicy, "-b"] + command
    return _launch_job(
        command,
        task_key=task_key,
        task_id=task_id,
        command_basename=command_basename,
        registry=reg,
        deps=dependencies,
        role=role,
        project_key=project_key,
        stop_event=stop_event,
    )


def _safe_registry_for_cli() -> Registry:
    registry = Registry(state_directory())
    registry.ensure_protocol()
    return registry


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the heavy command line and return the process exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if argv is None and not sys.flags.isolated:
        interpreter = "/usr/bin/python3"
        os.execv(
            interpreter, [interpreter, "-I", os.path.realpath(__file__)] + arguments
        )
    if arguments[:1] == ["--workload-bootstrap"]:
        if len(arguments) < 3 or not arguments[1].isdigit():
            return 125
        return _workload_bootstrap(int(arguments[1]), arguments[2:])
    if arguments[:1] == ["--watchdog"]:
        if len(arguments) != 2 or not JOB_ID_PATTERN.fullmatch(arguments[1]):
            return 64
        return _watchdog_main(arguments[1])
    role_flag = arguments[0] if arguments[:1] in (["--review"], ["--deploy"]) else None
    if role_flag:
        arguments = arguments[1:]
    if arguments in (["--help"], ["-h"]):
        print(
            "Usage: heavy [--review|--deploy] <command...> | status | request-curtail\n"
            "Runs one supervised workload per HERDR_PROJECTS_ID under fresh controller capacity. Deploy jobs enter ahead of reviews; jobs waiting over 10 minutes enter in arrival order. At most one deploy runs at a time.\n"
            "Admission requires stable swap, CPU and memory below 95%, and at least max(per-host headroom, 15% RAM) headroom to start or resume (a running job pauses only below max(per-host headroom, 12.5% RAM)); level 2 is allowed above 30% free memory, level 4 is blocked.\n"
            "Sustained host pressure or missing telemetry pauses the newest ordinary workload, resumes after 10 healthy seconds, and never resumes at zero controller capacity.\n"
            "status and request-curtail use JSON; request-curtail explicitly terminates the newest active job.\n"
            "Every job has a 45 minute wall-clock ceiling (HEAVY_MAX_RUNTIME_SECONDS may only lower it), enforced by the job's own watchdog and by every heavy call. A job terminated this way makes its heavy command exit 76."
        )
        return 0
    try:
        environment_role = os.environ.get("HEAVY_ROLE", "").strip().lower()
        if environment_role not in ("", "ordinary", "build", "test", "review"):
            raise HeavyError("HEAVY_ROLE must be review or ordinary")
        role = "deploy" if role_flag == "--deploy" else "review" if role_flag == "--review" or environment_role == "review" else "ordinary"
        if role_flag and arguments[:1] in (["status"], ["request-curtail"]):
            raise HeavyError("priority role requires a workload command")
        registry = _safe_registry_for_cli()
        _reap_over_limit(registry)
        if arguments[:1] == ["status"]:
            if len(arguments) != 1:
                raise HeavyError("usage: heavy status")
            print(
                json.dumps(
                    status_payload(registry), sort_keys=True, separators=(",", ":")
                )
            )
            return 0
        if arguments[:1] == ["request-curtail"]:
            if len(arguments) != 1:
                raise HeavyError("usage: heavy request-curtail")
            print(
                json.dumps(
                    _write_request_for_newest(registry),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        if not arguments:
            raise HeavyError(
                "usage: heavy [--review|--deploy] <command...> | status | request-curtail"
            )
        interrupted = {"signal": None}

        def on_signal(signum: int, _frame: Any) -> None:
            interrupted["signal"] = signum

        previous_int = signal.signal(signal.SIGINT, on_signal)
        previous_term = signal.signal(signal.SIGTERM, on_signal)
        try:
            return run_supervisor(
                arguments,
                registry=registry,
                role=role,
                stop_event=lambda: interrupted["signal"] is not None,
            )
        finally:
            signal.signal(signal.SIGINT, previous_int)
            signal.signal(signal.SIGTERM, previous_term)
    except HeavyError as exc:
        print("heavy: " + str(exc), file=sys.stderr)
        return 75
    except (OSError, ValueError, json.JSONDecodeError):
        print("heavy: local state or command failed safely", file=sys.stderr)
        return 74


def sample_with_emergency(
    *,
    command_runner: Callable[[Sequence[str], float], str] = _run_native,
    clock: Callable[[], float] = monotonic,
) -> Sample:
    """Sample host telemetry, attaching a partial sample to the error when a full one fails."""
    captured: Dict[str, str] = {}

    def capture(argv: Sequence[str], timeout: float) -> str:
        output = command_runner(argv, timeout)
        key = argv[-1] if argv[0] == "/usr/sbin/sysctl" else argv[0]
        captured[key] = output
        return output

    try:
        return sample_host(command_runner=capture, clock=clock)
    except TelemetryError as exc:
        pressure = physical = cores = headroom = memory_used = load = None
        try:
            pressure = parse_pressure_level(
                captured.get("kern.memorystatus_vm_pressure_level", "")
            )
        except TelemetryError:
            pass
        try:
            physical = int(captured.get("hw.memsize", ""))
            if physical <= 0:
                physical = None
        except ValueError:
            pass
        try:
            cores = int(captured.get("hw.physicalcpu", ""))
            if cores <= 0:
                cores = None
        except ValueError:
            pass
        if cores is not None:
            try:
                load = parse_load(captured.get("/usr/bin/uptime", ""), cores)
            except TelemetryError:
                pass
        if physical is not None:
            try:
                _, headroom = parse_vm_stat(captured.get("/usr/bin/vm_stat", ""))
                memory_used = (1 - headroom / physical) * 100
            except TelemetryError:
                pass
        partial = Sample(
            pressure_level=pressure,
            cpu_busy_pct=None,
            memory_used_pct=memory_used,
            headroom_bytes=headroom,
            physical_bytes=physical,
            load_per_core=load,
            captured_monotonic=clock(),
            physical_cores=cores,
        )
        if critical_pressure(partial, load_proxy=False):
            exc.partial_sample = partial
        raise


if __name__ == "__main__":
    sys.exit(main())
