"""ADMIN-ADDR-1 — the shared `admin` role must carry a machine axis.

`admin` is deliberately ONE role worn by a maintenance session on every box, so
the BARE string addresses all of them at once and the reader cannot tell which
one the sender meant. Measured on one box's inbox 2026-08-29: 149 of 200
messages were on the bare role, ~a quarter of those were box-specific work for a
DIFFERENT machine, and a session began another host's work from a request it had
no way to recognise as not-its-own.

The refusal is structural rather than advisory because discipline provably does
not hold: the roster offers only the bare identity and tells senders to use it,
`to` is unvalidated free text, and the cross-project reply rule routes to
`from_project` — the bare string for an admin sender. Three of the four routes
to this address are chosen by the system, not by the sender.

Two valid forms, both naming a machine axis:
  * `admin@<host>` — the maintenance session on one box
  * `admin@fleet`  — a DELIBERATE announcement to every admin session
"""

import pytest
from unittest.mock import patch

from server.services.identity import (
    ADMIN_FLEET,
    admin_listen_expansion,
    is_unqualified_admin,
)


async def _cleanup_inbox(db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM memories WHERE namespace='fleet' AND scope='inbox'"
        )


# ---------------------------------------------------------------- unit


def test_only_the_bare_role_is_unqualified():
    assert is_unqualified_admin("admin") is True
    assert is_unqualified_admin("  ADMIN  ") is True
    # Everything that names a target or declares a broadcast is fine.
    assert is_unqualified_admin("admin@hosta") is False
    assert is_unqualified_admin(ADMIN_FLEET) is False
    assert is_unqualified_admin("machine:hosta") is False
    assert is_unqualified_admin("admin-grok") is False
    assert is_unqualified_admin("administrator") is False
    assert is_unqualified_admin("engram") is False
    assert is_unqualified_admin("") is False
    assert is_unqualified_admin(None) is False


def test_expansion_only_fires_for_bare_role_listeners():
    # An admin session listening on the bare role gains the broadcast address.
    assert admin_listen_expansion(
        ["admin", "machine:hosta", "admin@hosta"]
    ) == [ADMIN_FLEET]
    # Idempotent: a swept bridge that already declares it gains nothing.
    assert admin_listen_expansion(["admin", ADMIN_FLEET]) == []
    # Non-admin readers are untouched.
    assert admin_listen_expansion(["engram", "machine:hostc"]) == []
    # Host-qualified-only listener is not a bare-role listener.
    assert admin_listen_expansion(["admin@hosta"]) == []


# ------------------------------------------------------- delivery (read side)


@pytest.mark.asyncio
async def test_admin_fleet_reaches_an_unswept_admin_session(client, db_pool):
    """The broadcast form must not wait on a bridge sweep.

    A bridge change lands only at the next session start, and admin sessions on
    quiet boxes live for weeks — so the server expands at READ time. This is the
    lesson the liveness arc already paid for: a client-side fix rescued no
    running session.
    """
    await _cleanup_inbox(db_pool)
    resp = await client.post("/memory/send", json={
        "to": ADMIN_FLEET,
        "subject": "fleet-wide notice",
        "body": "every box: rotate the thing",
        "from_": "engram@hostc",
    })
    assert resp.status_code == 200, resp.text
    msg_id = resp.json()["id"]

    # A PRE-SWEEP admin session: its listen_set has no `admin@fleet` in it.
    resp = await client.post("/memory/inbox", json={
        "listen_set": ["admin", "machine:hosta", "admin@hosta"],
        "reader_identity": "admin@hosta",
        "unread_only": True,
    })
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["messages"]]
    assert msg_id in ids, "admin@fleet must reach a session that predates the sweep"

    # A non-admin reader must NOT pick up fleet-wide admin mail.
    resp = await client.post("/memory/inbox", json={
        "listen_set": ["engram", "machine:hostc", "engram@hostc"],
        "reader_identity": "engram@hostc",
        "unread_only": True,
    })
    assert resp.status_code == 200
    assert msg_id not in [m["id"] for m in resp.json()["messages"]]

    await _cleanup_inbox(db_pool)


@pytest.mark.asyncio
async def test_host_qualified_admin_mail_stays_on_its_box(client, db_pool):
    """The property the whole item exists to protect."""
    await _cleanup_inbox(db_pool)
    resp = await client.post("/memory/send", json={
        "to": "admin@hosta",
        "subject": "hosta only",
        "body": "restart the hosta thing",
        "from_": "engram@hostc",
    })
    assert resp.status_code == 200, resp.text
    msg_id = resp.json()["id"]

    resp = await client.post("/memory/inbox", json={
        "listen_set": ["admin", "machine:hosta", "admin@hosta"],
        "reader_identity": "admin@hosta",
        "unread_only": True,
    })
    assert msg_id in [m["id"] for m in resp.json()["messages"]]

    # admin@hostb listens on the same bare role — and must not see it.
    resp = await client.post("/memory/inbox", json={
        "listen_set": ["admin", "machine:hostb", "admin@hostb"],
        "reader_identity": "admin@hostb",
        "unread_only": True,
    })
    assert msg_id not in [m["id"] for m in resp.json()["messages"]], \
        "host-qualified admin mail must not reach another box"

    await _cleanup_inbox(db_pool)


# ------------------------------------------------------- refusal (send side)


@pytest.mark.asyncio
async def test_bare_admin_is_accepted_while_the_gate_is_off(client, db_pool):
    """DEFAULT OFF is byte-identical to previous behaviour.

    Deployed bridges route cross-project replies to `from_project` — the bare
    string for an admin sender — so enforcing before the fleet is swept would
    refuse ordinary replies. OFF must therefore stay a no-op.
    """
    await _cleanup_inbox(db_pool)
    resp = await client.post("/memory/send", json={
        "to": "admin",
        "subject": "legacy path",
        "body": "still delivered while the gate is closed",
        "from_": "engram@hostc",
    })
    assert resp.status_code == 200, resp.text
    await _cleanup_inbox(db_pool)


@pytest.mark.asyncio
async def test_bare_admin_is_refused_loudly_when_enforced(client, db_pool):
    await _cleanup_inbox(db_pool)
    with patch("server.config.settings.require_qualified_admin", True):
        resp = await client.post("/memory/send", json={
            "to": "admin",
            "subject": "which box?",
            "body": "this cannot say which machine it means",
            "from_": "engram@hostc",
        })
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    # The refusal must TEACH the two valid forms, not merely reject.
    assert "admin@<host>" in detail
    assert ADMIN_FLEET in detail
    await _cleanup_inbox(db_pool)


@pytest.mark.asyncio
async def test_qualified_forms_survive_enforcement(client, db_pool):
    """Enforcement must not touch anything that names a machine axis."""
    await _cleanup_inbox(db_pool)
    with patch("server.config.settings.require_qualified_admin", True):
        for target in ("admin@hosta", ADMIN_FLEET, "machine:hosta",
                       "admin-grok", "engram"):
            resp = await client.post("/memory/send", json={
                "to": target,
                "subject": "fine",
                "body": "names a target",
                "from_": "engram@hostc",
            })
            assert resp.status_code == 200, f"{target} refused: {resp.text}"
    await _cleanup_inbox(db_pool)


@pytest.mark.asyncio
async def test_fanout_containing_bare_admin_is_refused(client, db_pool):
    """A list is the side door — one bad target must fail the whole send."""
    await _cleanup_inbox(db_pool)
    with patch("server.config.settings.require_qualified_admin", True):
        resp = await client.post("/memory/send", json={
            "to": ["engram", "admin"],
            "subject": "mixed",
            "body": "one target names no machine",
            "from_": "engram@hostc",
        })
    assert resp.status_code == 409, resp.text
    await _cleanup_inbox(db_pool)
