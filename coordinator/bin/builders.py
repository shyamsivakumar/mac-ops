"""The builders, in the order a build moves down them.

Builds run on GLM or MiniMax first, then DeepSeek Flash; never on an
OpenAI or Sol model (Shyam 2026-11-17). A builder that fails for a
blocking provider reason is held in the provider health store, so the next
build and the next send start on the next builder in the list until the
blocked one answers a probe.
"""

import provider_health

BUILDERS = (
    {"instanceId": "glm", "model": "zai/glm-5.3"},
    {"instanceId": "minimax", "model": "minimax/MiniMax-M3.1-Flash"},
    {"instanceId": "pi", "model": "deepseek/deepseek-flash"},
)


def identity(selection):
    return provider_health.identity(selection)


def same_builder(selection, instance, model):
    """Whether an instance and model name the given builder."""
    if not isinstance(selection, dict):
        return False
    if selection.get("instanceId") != instance:
        return False
    want = str(selection.get("model") or "").split("/")[-1]
    got = str(model or "").split("/")[-1]
    return bool(want) and want == got


def builder_for(selection):
    """The chain member a selection names, or None."""
    for member in BUILDERS:
        if same_builder(selection, member["instanceId"], member["model"]):
            return member
    return None


def is_builder(selection):
    return builder_for(selection) is not None


def ordered(preferred=None):
    """The builders in the order a build tries them.

    The builder the ticket names comes first, then the rest of the list
    in its own order. A selection that names no builder is not in the
    chain and adds nothing."""
    first = builder_for(preferred)
    rest = [member for member in BUILDERS if member is not first]
    return ([first] if first else []) + rest


def choose_builder(preferred=None, blocked=None):
    """The first builder that is not blocked, or None when all are.

    None means every builder is blocked: the caller waits for a probe
    instead of starting the work on a provider that cannot run it."""
    blocked = provider_health.blocked_identities() if blocked is None else set(blocked)
    for member in ordered(preferred):
        if identity(member) not in blocked:
            return member
    return None


def blocked_builder(selection, reason, now=None, reset_at=None):
    """Block a builder and return the log line, or None when already blocked."""
    return provider_health.block(selection, reason, now=now, reset_at=reset_at)


def recovered_builder(selection, request_id=None):
    """Unblock a builder after a successful probe."""
    return provider_health.unblock(selection, request_id=request_id)
