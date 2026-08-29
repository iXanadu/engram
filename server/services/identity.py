"""Inbox addressing and identity helpers.

An inbox "address" is a flat string that identifies a logical recipient:

- ``engram``            — any Claude working in the engram project
- ``machine:hosta``   — any Claude on hosta (typically admin sessions)
- ``topic:refactor-x``  — anyone subscribed to that topic (future)

A running Claude session listens on a **set** of addresses (its ``listen_set``)
computed by the MCP bridge at startup from ``$CWD``, ``$HOME``, and
``hostname``. The server trusts whatever the client sends — the MCP bridge
has perfect information about its own environment, and this is internal
single-principal infrastructure.
"""

import re

RESERVED_PREFIXES = ("machine:", "topic:")

# ADMIN-ADDR-1 — the shared `admin` role and its two legitimate forms.
#
# `admin` is deliberately ONE role worn by maintenance sessions on every box
# (it is exempt from seat-collision detection for exactly that reason). That
# makes the BARE string `admin` an address every admin session on the fleet
# listens on — so a request meant for one box is delivered to all of them, and
# the reader cannot tell which. Measured 2026-08-29 on one box's inbox: 149 of
# 200 messages went to the bare role, and roughly a quarter of those were
# box-specific work for a DIFFERENT machine. The cost is not noise; a session
# started on one host and began another host's work from a request it had no
# way to recognise as not-its-own.
#
# The fix is structural rather than advisory, because discipline provably does
# not hold here: the roster offers only the bare `admin` identity and tells
# senders to address it, `to` is free text with no validation, and the
# cross-project reply rule routes replies to `from_project` — which for an
# admin session IS the bare string. Three of the four routes to this address
# are chosen by the system, not the sender.
#
# Two forms are valid, and both say which machine they mean:
#   * `admin@<host>` — the maintenance session on ONE box.
#   * `admin@fleet`  — a DELIBERATE announcement to every admin session. The
#                      broadcast still exists; it just has to be typed. What
#                      is refused is the form that cannot distinguish "all of
#                      you" from "whichever of you I meant".
ADMIN_ROLE = "admin"
FLEET_QUALIFIER = "fleet"
ADMIN_FLEET = f"{ADMIN_ROLE}@{FLEET_QUALIFIER}"
# Leading '#' marks a cross-project coalition CHANNEL (e.g. '#courseware'):
# a named address distinct from any project, that agents from different
# projects subscribe to at launch. The sigil keeps channels from colliding
# with project names in the flat address space (mirrors the reserved
# 'machine:' prefix). See docs/messaging.md.
ADDRESS_RE = re.compile(r"^#?[a-zA-Z0-9][a-zA-Z0-9_.\-:@]{0,127}$")


def validate_address(address: str) -> str:
    """Return the address if valid, else raise ValueError.

    Addresses must be non-empty, <=128 chars, and match ``ADDRESS_RE``.
    Reserved prefixes (``machine:``, ``topic:``) are allowed — senders may
    target them intentionally. A leading ``#`` marks a coalition channel.
    """
    if not isinstance(address, str) or not address.strip():
        raise ValueError("address must be a non-empty string")
    address = address.strip().lower()
    if not ADDRESS_RE.match(address):
        raise ValueError(f"invalid address: {address!r}")
    return address


def autocorrect_address(address: str) -> tuple[str, str | None]:
    """Validate and auto-correct common addressing mistakes.

    Returns ``(corrected_address, original_or_none)``.  When no correction
    is needed, ``original_or_none`` is ``None``.

    Corrections:
    - ``admin:host`` → ``machine:host`` (admin targeting a host)
    - ``host:project`` → ``project`` (strip host qualifier, broadcast)
    """
    clean = validate_address(address)
    if ":" not in clean:
        return clean, None
    if any(clean.startswith(p) for p in RESERVED_PREFIXES):
        return clean, None
    # Non-reserved colon — likely a mis-formatted address
    original = clean
    left, right = clean.split(":", 1)
    if left == "admin":
        return f"machine:{right}", original
    if right == "admin":
        return f"machine:{left}", original
    # Assume left is a host qualifier, right is the project name
    return right, original


def is_unqualified_admin(address: str) -> bool:
    """True when ``address`` is the bare shared role with no machine axis.

    Only the exact bare string qualifies. ``admin@<host>``, ``admin@fleet``,
    ``machine:<host>`` and every seat-shaped address (``admin-grok``) are
    fine — they all name a specific target or declare a deliberate broadcast.
    """
    return isinstance(address, str) and address.strip().lower() == ADMIN_ROLE


def admin_listen_expansion(listen_set: list[str]) -> list[str]:
    """Addresses to ADD for a reader so `admin@fleet` reaches it.

    Returns extra addresses, never a replacement — callers append.

    Delivery of the new broadcast form must not wait on a bridge sweep. A
    bridge change only lands at the next session start, so an admin session
    running right now would be deaf to `admin@fleet` for as long as it lives
    (and admin sessions on quiet boxes live for weeks). This project has
    already paid for that lesson once: a client-side liveness fix rescued no
    running session, and the server-side version healed them on one call.

    So the server expands at READ time: any reader already listening on the
    bare role also matches `admin@fleet`, on every deployed bridge, from the
    moment this deploys.
    """
    if any(is_unqualified_admin(a) for a in listen_set):
        if ADMIN_FLEET not in listen_set:
            return [ADMIN_FLEET]
    return []


def validate_listen_set(addresses: list[str]) -> list[str]:
    """Validate and normalize a list of addresses. Empty list is allowed."""
    if addresses is None:
        return []
    if not isinstance(addresses, list):
        raise ValueError("listen_set must be a list of strings")
    return [validate_address(a) for a in addresses]
