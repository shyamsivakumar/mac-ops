"""The one model list.

`models.json` is the only place a model is listed. The ticket tool, coordq,
the lane driver and the pi route generator read it through this module.
Lists: `build` (every build type; an entry's optional `leads` names the task types it goes first for), `fix` (fix and finish rounds), `review`
(the gate) and `panel` (only when Shyam asks for one).

A provider that fails for a blocking reason is recorded in
`providers-blocked.json` in the queue folder, so every caller skips the same
blocked providers. `block_provider` writes an entry with an `expires_at`
epoch time; the reader drops an entry once that time has passed. An entry
without a numeric `expires_at` is a manual block and stays until removed.
"""

import contextlib
import fcntl
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

LISTS = ("build", "fix", "review", "panel")
INSTALLED_PATH = "~/.coordinator/models.json"
SEED_PATH = Path(__file__).resolve().parent.parent / "models.json"
BLOCKED_FILE = "providers-blocked.json"
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
            leads = entry.get("leads", [])
            if not (isinstance(leads, list) and all(nonempty_string(t) for t in leads)):
                raise ModelsError(f"models.json {name} entry leads must be a list of task types: {entry!r}")
            if entry["id"] in seen:
                raise ModelsError(f"models.json {name} lists {entry['id']} twice")
            seen.add(entry["id"])
    return data


def reject_constant(token):
    raise ValueError(f"{token} is not a JSON value")


def read_json(file_path):
    """The parsed file. A missing file raises FileNotFoundError; any other failure to read it is a ModelsError."""
    try:
        with open(file_path) as f:
            return json.load(f, parse_constant=reject_constant)
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


def blocked_path():
    queue = os.environ.get("COORDQ_DIR", os.path.expanduser("~/Code/coordinator/queue"))
    return os.path.join(queue, BLOCKED_FILE)


def read_blocked_file(file_path):
    try:
        data = read_json(file_path)
    except FileNotFoundError:
        return {"blocked": {}}
    if not isinstance(data, dict) or not isinstance(data.get("blocked"), dict):
        raise ModelsError(f"{BLOCKED_FILE} must hold a blocked object")
    return data


def expiry(entry):
    """The entry's `expires_at` as a float, or infinity for a manual entry that never expires.

    Anything that is not a finite number counts as manual, including an integer too
    large for a float, which JavaScript's JSON.parse reads as an infinity.
    """
    value = entry.get("expires_at") if isinstance(entry, dict) else None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return math.inf
    try:
        seconds = float(value)
    except OverflowError:
        return math.inf
    return seconds if math.isfinite(seconds) else math.inf


def blocked_identities(now=None):
    now = time.time() if now is None else now
    blocked = read_blocked_file(blocked_path())["blocked"]
    return {key for key, entry in blocked.items() if expiry(entry) > now}


@contextlib.contextmanager
def blocked_lock():
    """Hold the lock `block_provider` takes, so a caller that reads the block
    list sees no block recorded until it releases. `block_provider` cannot run
    under it in the same process."""
    with open(blocked_path() + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def block_provider(selection, expires_at, now=None):
    """Block a provider until `expires_at` (epoch seconds), keeping every other entry.

    A manual block or a longer block is kept, so a late refusal never releases
    a provider early. A file that cannot be parsed is left alone and refused.
    """
    key = identity(selection)
    if not key or expiry({"expires_at": expires_at}) == math.inf:
        raise ModelsError(f"block_provider needs a selection and a finite expires_at: {selection!r}, {expires_at!r}")
    now = time.time() if now is None else now
    file_path = blocked_path()
    with blocked_lock():
        try:
            data = read_blocked_file(file_path)
        except ModelsError as e:
            print(f"models: refusing to write {file_path}: {e}", file=sys.stderr)
            raise
        blocked = {k: v for k, v in data["blocked"].items() if expiry(v) > now}
        if expires_at <= now or (key in blocked and expiry(blocked[key]) >= expires_at):
            return
        data["blocked"] = {**blocked, key: {**blocked.get(key, {}), "expires_at": expires_at}}
        try:
            text = json.dumps(data, allow_nan=False)
        except ValueError as e:
            print(f"models: refusing to write {file_path}: {e}", file=sys.stderr)
            raise ModelsError(f"{BLOCKED_FILE} holds a number JSON cannot store: {e}") from e
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(file_path), prefix=f".{BLOCKED_FILE}.")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, file_path)
        except BaseException:
            os.unlink(tmp)
            raise


def is_blocked(selection, blocked=None):
    blocked = blocked_identities() if blocked is None else blocked
    return identity(selection) in blocked


def in_order(list_name, preferred=None, task_type=None):
    """The entries of a list: the preferred id first, then the entries whose
    `leads` names the task type, then the rest, each group in list order."""
    def rank(entry):
        if entry["id"] == preferred:
            return 0
        return 1 if task_type in entry.get("leads", ()) else 2

    return sorted(entries(list_name), key=rank)


def first_available(list_name, preferred=None, blocked=None, task_type=None):
    """The first entry that is not blocked, or None when every entry is."""
    blocked = blocked_identities() if blocked is None else blocked
    for entry in in_order(list_name, preferred, task_type):
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


def pi_routes(task_type=None):
    """The build list as pi route specs, `provider/model`, in the order the
    task type uses.

    Only an entry whose model carries a pi provider prefix can run in pi."""
    return [
        e["selection"]["model"]
        for e in in_order("build", task_type=task_type)
        if "/" in e["selection"]["model"]
    ]


def pi_identities():
    """The blocked-store identity of each pi route spec, so pi can skip a blocked provider."""
    return {
        e["selection"]["model"]: identity(e["selection"])
        for e in entries("build")
        if "/" in e["selection"]["model"]
    }


def first_other(list_name, own_model=None):
    """The first unblocked entry whose model is not `own_model` (a model name, any provider prefix)."""
    own = str(own_model or "").split("/")[-1]
    blocked = blocked_identities()
    for entry in entries(list_name):
        if entry["selection"]["model"].split("/")[-1] != own and identity(entry["selection"]) not in blocked:
            return entry
    return None


def main(argv):
    if len(argv) not in (3, 4) or argv[1] != "first" or argv[2] not in LISTS:
        print(f"usage: models.py first {{{'|'.join(LISTS)}}} [own-model]", file=sys.stderr)
        return 2
    entry = first_other(argv[2], argv[3] if len(argv) == 4 else None)
    if entry is None:
        print(f"no unblocked model in the {argv[2]} list", file=sys.stderr)
        return 1
    print(f"{entry['id']} {entry['selection']['model']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
