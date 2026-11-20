"""The one model list.

`models.json` is the only place a model is listed. The ticket tool, coordq,
the lane driver and the pi route generator read it through this module.
Lists: `build` (every build type; an entry's optional `leads` names the task types it goes first for and `only` the task types it serves), `fix` (fix and finish rounds), `review`
(the gate) and `panel` (only when Shyam asks for one).

A provider that fails for a blocking reason is recorded in
`providers-blocked.json` in the queue folder, so every caller skips the same
blocked providers. `block_provider` writes an entry with an `expires_at`
epoch time; the reader drops an entry once that time has passed. An entry
written before that rule carries only an ISO 8601 `until`, which the reader
honours when `expires_at` is absent. An entry with neither is a manual block
and stays until removed. The reader also drops an entry whose model is no
longer listed in `models.json`.
"""

import contextlib
import datetime
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
# A router entry names the T3 `router` instance and a route, `task/<chain>`.
# The chain table says which models that route tries, in order, so the order
# inside Morph is owned by the router and the order after Morph by this file.
ROUTER_INSTANCE = "router"
ROUTE_PREFIX = "task/"
DEFAULT_CHAIN = "standard"


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
            for key in ("leads", "only"):
                types = entry.get(key, [])
                if not (isinstance(types, list) and all(nonempty_string(t) for t in types)):
                    raise ModelsError(f"models.json {name} entry {key} must be a list of task types: {entry!r}")
            if is_router(entry):
                validate_router(entry, name)
            if entry["id"] in seen:
                raise ModelsError(f"models.json {name} lists {entry['id']} twice")
            seen.add(entry["id"])
    return data


def reject_constant(token):
    raise ValueError(f"{token} is not a JSON value")


def is_router(entry):
    """Whether an entry runs on the T3 router instance."""
    selection = entry.get("selection") if isinstance(entry, dict) else None
    return isinstance(selection, dict) and selection.get("instanceId") == ROUTER_INSTANCE


def validate_router(entry, list_name):
    """A router entry needs a chain table and a route table that names it."""
    chains = entry.get("chains")
    if not isinstance(chains, dict) or not chains:
        raise ModelsError(f"models.json {list_name} router entry needs a non-empty chains table: {entry!r}")
    for chain, models in chains.items():
        if not (nonempty_string(chain) and isinstance(models, list) and models
                and all(nonempty_string(model) for model in models)):
            raise ModelsError(f"models.json {list_name} router chain {chain!r} must be a non-empty list of models: {entry!r}")
    routes = entry.get("routes")
    if not isinstance(routes, dict) or not routes:
        raise ModelsError(f"models.json {list_name} router entry needs a non-empty routes table: {entry!r}")
    for task_type, chain in routes.items():
        if not (nonempty_string(task_type) and nonempty_string(chain) and chain in chains):
            raise ModelsError(f"models.json {list_name} router route {task_type!r} must name a chain: {entry!r}")
    if DEFAULT_CHAIN not in chains:
        raise ModelsError(f"models.json {list_name} router entry needs a {DEFAULT_CHAIN!r} chain: {entry!r}")


def chain_of(entry, task_type=None):
    """The chain a router entry runs for a task type, `standard` when the type names none."""
    routes = entry.get("routes") or {}
    return routes.get(task_type) or DEFAULT_CHAIN


def router_route(selection):
    """The chain a router selection names, or None when it names none."""
    model = str(selection.get("model") or "") if isinstance(selection, dict) else ""
    return model[len(ROUTE_PREFIX):] if model.startswith(ROUTE_PREFIX) else None


def route_of(entry, task_type=None):
    """The router route a task type runs, `task/<chain>`."""
    return f"{ROUTE_PREFIX}{chain_of(entry, task_type)}"


def selection_for(entry, task_type=None):
    """The selection an entry runs for a task type.

    A router entry names the route for the type, so one entry serves every
    chain; every other entry names its own selection."""
    if is_router(entry):
        return {**entry["selection"], "model": route_of(entry, task_type)}
    return entry["selection"]


def chain_models(entry):
    """Every model a router entry can run, in chain order, without repeats."""
    models = []
    for chain in (entry.get("chains") or {}).values():
        for model in chain:
            if model not in models:
                models.append(model)
    return models


def pi_identity(model):
    """The blocked-store identity of a model the `pi` instance runs."""
    return identity({"instanceId": "pi", "model": model})


def entry_identities(entry):
    """The blocked-store identities an entry covers.

    A router entry covers one identity per Morph model in its chains, so it is
    blocked only when every one of them is blocked."""
    if is_router(entry):
        return {pi_identity(model) for model in chain_models(entry)}
    return {identity(entry["selection"])}


def entry_blocked(entry, blocked=None):
    """Whether every identity an entry covers is blocked."""
    blocked = blocked_identities() if blocked is None else blocked
    return entry_identities(entry) <= blocked


def router_entry(list_name):
    """The router entry of a list, or None when the list has none."""
    for entry in entries(list_name):
        if is_router(entry):
            return entry
    return None


def router_covers(list_name, selection):
    """The router entry of a list when it runs the model a selection names.

    A caller that still sends a direct `pi` Morph model is mapped to the
    router entry, so the launch goes through the router and its fallback. The
    match is on the blocked-store identity, so a model of another instance
    never counts."""
    entry = router_entry(list_name)
    if entry is None or not isinstance(selection, dict):
        return None
    return entry if identity(selection) in entry_identities(entry) else None


def selection_identities(selection, list_name="build"):
    """The identities to block so the entry a selection names is skipped.

    A router selection names one entry that covers every Morph model, so
    skipping it means blocking each of them."""
    entry = find(selection, (list_name,))
    return entry_identities(entry) if entry is not None else {identity(selection)}


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


def moment(value):
    """The epoch second an ISO 8601 timestamp names, or None when it names none."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        stamp = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.timestamp()


def expiry(entry):
    """The epoch second the entry stops blocking, or infinity for a manual entry.

    `expires_at` is the epoch second `block_provider` writes. An entry written
    before that rule carries only an ISO 8601 `until`, so `until` is read when
    `expires_at` is absent. Anything that is not a finite number counts as
    manual, including an integer too large for a float, which JavaScript's
    JSON.parse reads as an infinity.
    """
    if not isinstance(entry, dict):
        return math.inf
    if "expires_at" in entry:
        value = entry["expires_at"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return math.inf
        try:
            seconds = float(value)
        except OverflowError:
            return math.inf
        return seconds if math.isfinite(seconds) else math.inf
    until = moment(entry.get("until"))
    return math.inf if until is None else until


def known_identities():
    """Every blocked-store identity a list can produce.

    An entry whose key is not one of these names a model no list carries any
    more, so the reader drops it instead of keeping a stale block forever."""
    known = set()
    for name in LISTS:
        for entry in entries(name):
            known |= entry_identities(entry)
    return known


def blocked_identities(now=None):
    now = time.time() if now is None else now
    blocked = read_blocked_file(blocked_path())["blocked"]
    known = known_identities()
    return {key for key, entry in blocked.items() if key in known and expiry(entry) > now}


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
    `leads` names the task type, then the rest, each group in list order.

    With a task type, an entry whose `only` omits it is left out unless it is
    the preferred id."""
    def rank(entry):
        if entry["id"] == preferred:
            return 0
        return 1 if task_type in entry.get("leads", ()) else 2

    listed = [
        e for e in entries(list_name)
        if e["id"] == preferred or task_type is None or "only" not in e or task_type in e["only"]
    ]
    return sorted(listed, key=rank)


def first_available(list_name, preferred=None, blocked=None, task_type=None):
    """The first entry that is not blocked, or None when every entry is."""
    blocked = blocked_identities() if blocked is None else blocked
    for entry in in_order(list_name, preferred, task_type):
        if not entry_blocked(entry, blocked):
            return entry
    return None


def find(selection, list_names=LISTS):
    """The entry a selection names.

    A router selection names the router entry of the list when it carries a
    configured route, because one entry owns every route."""
    wanted = identity(selection)
    chain = router_route(selection) if isinstance(selection, dict) else None
    for name in list_names:
        for entry in entries(name):
            if identity(entry["selection"]) == wanted:
                return entry
            if chain is not None and is_router(entry) and chain in (entry.get("chains") or {}):
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

    A router entry contributes the models of the chain its route names, so the
    installer rebuilds the router's own table from this file. Only an entry
    whose model carries a pi provider prefix can run in pi."""
    specs = []
    for entry in in_order("build", task_type=task_type):
        if is_router(entry):
            specs += (entry.get("chains") or {}).get(chain_of(entry, task_type), [])
        elif "/" in entry["selection"]["model"]:
            specs.append(entry["selection"]["model"])
    return specs


def pi_identities():
    """The blocked-store identity of each pi route spec, so pi can skip a blocked provider."""
    identities = {}
    for entry in entries("build"):
        if is_router(entry):
            for model in chain_models(entry):
                identities[model] = pi_identity(model)
        elif "/" in entry["selection"]["model"]:
            identities[entry["selection"]["model"]] = identity(entry["selection"])
    return identities


def first_other(list_name, own_model=None):
    """The first unblocked entry whose model is not `own_model` (a model name, any provider prefix)."""
    own = str(own_model or "").split("/")[-1]
    blocked = blocked_identities()
    for entry in entries(list_name):
        if entry["selection"]["model"].split("/")[-1] != own and not entry_blocked(entry, blocked):
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
