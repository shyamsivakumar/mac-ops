"""The one model list.

`models.json` is the only place a model is listed. The ticket tool, coordq,
the lane driver and the pi route generator read it through this module.
Lists: `build` (every build type), `fix` (fix and finish rounds), `review`
(the gate) and `panel` (only when Shyam asks for one).

A provider that fails for a blocking reason is recorded in one place,
`providers-blocked.json` in the queue folder. This module reads that file
and writes it, so every caller skips the same blocked providers, and a
block ends at the reset the provider named.
"""

import fcntl
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LISTS = ("build", "fix", "review", "panel")
INSTALLED_PATH = "~/.coordinator/models.json"
SEED_PATH = Path(__file__).resolve().parent.parent / "models.json"
BLOCKED_FILE = "providers-blocked.json"
BLOCKED_LOCK = "providers-blocked.lock"
BLOCK_SECONDS = 3600.0
UNITS = {"d": 86400.0, "h": 3600.0, "m": 60.0, "s": 1.0}
AMOUNT = r"(\d+(?:\.\d+)?)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b"
RELATIVE = re.compile(rf"(?:resets?|retry|try(?:\s+again)?)\s+(?:in|after)\s+((?:{AMOUNT}[\s,]*(?:and\s+)?)+)", re.I)
# A reset the provider names as a clock time: "resets at 14:00 UTC", "resets
# at 3:20am (America/Los_Angeles)", "will reset at 2026-11-18 11:58:52
# (Asia/Shanghai)". The zone is the one the message states beside the clock:
# an offset, then a named zone, then a bare UTC.
ZONE_TEXT = r"(?:UTC|GMT)?[+-]\d{2}:?\d{2}|[A-Za-z_]+(?:/[A-Za-z0-9_+-]+)+|UTC|GMT|Z\b"
ABSOLUTE = re.compile(
    r"reset(?:s|ting at| at)?\s+(?:at\s+)?(?:(\d{4}-\d{2}-\d{2})[ T])?(\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?:\s*([ap]\.?m\.?)(?![A-Za-z]))?"
    rf"(?:\s*\(\s*({ZONE_TEXT})\s*\)|\s*({ZONE_TEXT}))?", re.I)
PROVIDER_ERROR = re.compile(
    r"\b(?:http|status|error(?:\s+code)?)\b[\s:=]*(?:401|402|403|429)\b"
    r"|\"code\"\s*:\s*(?:401|402|403|429)\b"
    r"|^\s*(?:401|402|403|429)(?=\s*(?:$|[;:,.-]|unauthorized|forbidden|too many|payment))"
    r"|(?:usage limit|rate limit|too many requests|no credits|out of credits|credit balance"
    r"|insufficient[_ ]quota|quota (?:exceeded|exhausted)|payment required|invalid api key"
    r"|authentication_error)(?:ed|s)?(?!\w|\.\w)",
    re.I,
)
LOCAL_ERROR = re.compile(r"disk quota|no space left|enospc|disk full|no such file|filenotfounderror", re.I)
EXIT_CODE = re.compile(r"\b(?:exit(?:ed)?|return(?:ed)?)\b[\s\w-]{0,20}?\b(?:code|status)\s*[:=]?\s*\d+|\breturn ?code\s*[:=]?\s*\d+", re.I)
VENDOR_PREFIXES = (("claude", "anthropic"), ("gpt", "openai"), ("o3", "openai"), ("o4", "openai"))


class ModelsError(ValueError):
    pass


def path():
    override = os.environ.get("COORDINATOR_MODELS")
    if override:
        return Path(override)
    installed = Path(os.path.expanduser(INSTALLED_PATH))
    return installed if installed.exists() else SEED_PATH


def nonempty_string(value):
    return isinstance(value, str) and bool(value)


def validate(data):
    if not isinstance(data, dict):
        raise ModelsError("models.json must be an object")
    for name in LISTS:
        entries = data.get(name)
        if not isinstance(entries, list) or not entries:
            raise ModelsError(f"models.json needs a non-empty {name} list")
        seen = set()
        for entry in entries:
            selection = entry.get("selection") if isinstance(entry, dict) else None
            if not (
                isinstance(selection, dict)
                and all(nonempty_string(selection.get(key)) for key in ("instanceId", "model"))
                and all(nonempty_string(entry.get(key)) for key in ("id", "vendor"))
            ):
                raise ModelsError(
                    f"models.json {name} entry needs id, vendor and a selection with instanceId and model: {entry!r}"
                )
            if entry["id"] in seen:
                raise ModelsError(f"models.json {name} lists {entry['id']} twice")
            seen.add(entry["id"])
    return data


def read_json(file_path):
    """The parsed file. A missing file raises FileNotFoundError; any other failure to read it is a ModelsError."""
    try:
        with open(file_path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise
    except OSError as e:
        raise ModelsError(f"{file_path} cannot be read: {e}") from e
    except ValueError as e:
        raise ModelsError(f"{file_path} is not valid JSON text: {e}") from e


def load():
    try:
        return validate(read_json(path()))
    except FileNotFoundError as e:
        raise ModelsError(f"{path()} does not exist") from e


def entries(list_name):
    return load()[list_name]


def identity(selection):
    """`instanceId:model`, the model on its last segment, so a provider
    prefixed spelling names the same provider as the plain one."""
    if not isinstance(selection, dict):
        return ""
    instance = selection.get("instanceId")
    model = str(selection.get("model") or "").split("/")[-1]
    return f"{instance}:{model}" if instance and model else ""


def same_selection(a, b):
    """Whether two selections name the same provider and the exact same model string."""
    return (isinstance(a, dict) and isinstance(b, dict) and bool(a.get("instanceId")) and bool(a.get("model"))
            and a.get("instanceId") == b.get("instanceId") and a.get("model") == b.get("model"))


def queue_dir():
    return os.environ.get("COORDQ_DIR", os.path.expanduser("~/Code/coordinator/queue"))


def read_blocked():
    try:
        data = read_json(os.path.join(queue_dir(), BLOCKED_FILE))
    except FileNotFoundError:
        return {}
    blocked = data.get("blocked") if isinstance(data, dict) else None
    if not isinstance(blocked, dict):
        raise ModelsError(f"{BLOCKED_FILE} must hold a blocked object")
    return blocked


def live(entry, now):
    until = entry.get("until") if isinstance(entry, dict) else None
    return not isinstance(until, (int, float)) or until > now


def blocked_identities(now=None):
    now = time.time() if now is None else now
    return {name for name, entry in read_blocked().items() if live(entry, now)}


def zone_of(text):
    """The zone a message names, as a zoneinfo zone or a fixed offset."""
    if not text or text.upper() in ("UTC", "GMT", "Z"):
        return timezone.utc
    if "/" in text:
        return ZoneInfo(text)
    sign, digits = ("-" if "-" in text else "+"), re.sub(r"\D", "", text)
    offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4]))
    return timezone(-offset if sign == "-" else offset)

def reset_at(message, failed):
    """Epoch seconds of the reset a provider error names, else an hour after the failure."""
    relative = RELATIVE.search(message)
    if relative:
        return failed + sum(float(n) * UNITS[u[0].lower()] for n, u in re.findall(AMOUNT, relative.group(1), re.I))
    absolute = ABSOLUTE.search(message)
    if absolute:
        day, clock, meridiem, parenthesised, zone_text = absolute.groups()
        try:
            zone = zone_of(parenthesised or zone_text)
            hour, _, rest = clock.partition(":")
            hour = int(hour)
            if meridiem:
                if meridiem.lower().startswith("p") and hour < 12:
                    hour += 12
                elif meridiem.lower().startswith("a") and hour == 12:
                    hour = 0
            local_day = day or datetime.fromtimestamp(failed, zone).date().isoformat()
            local = datetime.fromisoformat(f"{local_day}T{hour:02d}:{rest}")
            until = local.replace(tzinfo=zone).timestamp()
            if not day and until <= failed:
                # The clock time has passed today, so the reset is the same
                # clock time tomorrow. The local calendar date moves first
                # and the zone is applied after, so a day that changes its
                # offset still holds the provider for the window it names.
                until = (local + timedelta(days=1)).replace(tzinfo=zone).timestamp()
        except (ValueError, KeyError):
            return failed + BLOCK_SECONDS
        if until > failed:
            return until
    return failed + BLOCK_SECONDS


@contextmanager
def blocked_lock():
    with open(os.path.join(queue_dir(), BLOCKED_LOCK), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def block_provider(selection, error, failed=None):
    """Record a provider that refused a run, until the reset its error names.

    Returns False and records nothing when the error is no provider refusal."""
    name = identity(selection)
    if not name or not PROVIDER_ERROR.search(EXIT_CODE.sub(" ", error)) or LOCAL_ERROR.search(error):
        return False
    failed = time.time() if failed is None else failed
    with blocked_lock():
        blocked = {n: e for n, e in read_blocked().items() if live(e, time.time())}
        entry = {"failed": failed, "until": reset_at(error, failed)}
        held = blocked.get(name)
        if isinstance(held, dict) and isinstance(held.get("until"), (int, float)) and held["until"] >= entry["until"]:
            return True
        blocked[name] = entry
        target = os.path.join(queue_dir(), BLOCKED_FILE)
        with open(f"{target}.tmp", "w") as f:
            json.dump({"blocked": blocked}, f, indent=2)
        os.replace(f"{target}.tmp", target)
    return True


def is_blocked(selection, blocked=None):
    blocked = blocked_identities() if blocked is None else blocked
    return identity(selection) in blocked


def in_order(list_name, preferred=None):
    """The entries of a list, the preferred id first, then the list in order."""
    listed = entries(list_name)
    first = [e for e in listed if e["id"] == preferred]
    return first + [e for e in listed if e["id"] != preferred]


def first_available(list_name, preferred=None, blocked=None):
    """The first entry that is not blocked, or None when every entry is."""
    blocked = blocked_identities() if blocked is None else blocked
    for entry in in_order(list_name, preferred):
        if identity(entry["selection"]) not in blocked:
            return entry
    return None


def find(selection, list_names=LISTS):
    wanted = identity(selection)
    for name in list_names:
        for entry in entries(name):
            if identity(entry["selection"]) == wanted:
                return entry
    return None


def vendor_of(model):
    """The vendor of an executed model, given as a selection or a model name.

    A router entry carries a thinking level after a colon, which is not part
    of the model name."""
    if isinstance(model, dict):
        entry = find(model)
        return entry["vendor"] if entry else None
    name = str(model or "").split("/")[-1].split(":")[0]
    for list_name in LISTS:
        for entry in entries(list_name):
            if entry["selection"]["model"].split("/")[-1] == name:
                return entry["vendor"]
    lowered = name.lower()
    for prefix, vendor in VENDOR_PREFIXES:
        if lowered.startswith(prefix):
            return vendor
    return None


def reviewers(builder_models=(), preferred=None, blocked=None):
    """The gate reviewers a build may use, in order.

    A reviewer of the builder's vendor is skipped, and so is a blocked
    one. A builder model of unknown vendor excludes nothing."""
    blocked = blocked_identities() if blocked is None else blocked
    vendors = {vendor_of(m) for m in builder_models} - {None}
    return [
        e
        for e in in_order("review", preferred)
        if e["vendor"] not in vendors and identity(e["selection"]) not in blocked
    ]


def pi_routes():
    """The build list as pi route specs, `provider/model`, in order.

    Only an entry whose model carries a pi provider prefix can run in pi."""
    return [
        e["selection"]["model"]
        for e in entries("build")
        if "/" in e["selection"]["model"]
    ]


def pi_identities():
    """The blocked-store identity of each pi route spec, so pi can skip a blocked provider."""
    return {
        e["selection"]["model"]: identity(e["selection"])
        for e in entries("build")
        if "/" in e["selection"]["model"]
    }
