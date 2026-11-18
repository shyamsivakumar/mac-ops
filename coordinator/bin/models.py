"""The one model list.

`models.json` is the only place a model is listed. The ticket tool, coordq,
the lane driver and the pi route generator read it through this module.
Lists: `build` (every build type), `fix` (fix and finish rounds), `review`
(the gate) and `panel` (only when Shyam asks for one).

A provider that fails for a blocking reason is recorded by the provider
health store, `providers-blocked.json` in the queue folder. This module
only reads that file, so every caller skips the same blocked providers.

A caller that reads the blocked set and then acts on it holds
`blocked_lock()`, the lock every writer of the store holds too. A block
recorded while that lock is held cannot land between the decision and the
action it decided on.
"""

import contextlib
import fcntl
import json
import os
from pathlib import Path

LISTS = ("build", "fix", "review", "panel")
INSTALLED_PATH = "~/.coordinator/models.json"
SEED_PATH = Path(__file__).resolve().parent.parent / "models.json"
BLOCKED_FILE = "providers-blocked.json"
BLOCKED_LOCK_FILE = "providers-blocked.lock"
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
    """The queue folder, where the block store and its lock live."""
    return os.environ.get("COORDQ_DIR", os.path.expanduser("~/Code/coordinator/queue"))


@contextlib.contextmanager
def blocked_lock():
    """The lock on the provider block store.

    A caller holds it while it reads the blocked set and acts on the
    answer, so a block recorded in between cannot slip past the decision.
    The store's writer holds the same lock while it writes, so the two
    never overlap. The lock is taken before the queue lock, everywhere.
    """
    directory = queue_dir()
    os.makedirs(directory, exist_ok=True)
    handle = open(os.path.join(directory, BLOCKED_LOCK_FILE), "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        handle.close()


def blocked_identities():
    queue = queue_dir()
    try:
        data = read_json(os.path.join(queue, BLOCKED_FILE))
    except FileNotFoundError:
        return set()
    blocked = data.get("blocked") if isinstance(data, dict) else None
    if not isinstance(blocked, dict):
        raise ModelsError(f"{BLOCKED_FILE} must hold a blocked object")
    return set(blocked)


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
