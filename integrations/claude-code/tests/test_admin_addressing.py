"""ADMIN-ADDR-1, bridge half — keep the machine axis on admin mail.

`admin` is ONE role worn by a maintenance session on every box. Two routing
rules in this bridge used to strip the host and produce the bare role WITHOUT
anyone choosing it:

  * ``reader_to_address`` returns the name-part of ``<name>@<host>``, so
    ``admin@hosta`` became ``admin``;
  * the cross-project rule (O2) routes a reply to ``from_project``, which for
    an admin sender IS the bare string.

Both are correct for an ordinary project — a project channel SHOULD reach every
session on it. They are wrong for admin, whose sessions sit on different
machines doing unrelated work. This is why the fix had to be structural: a
sender who never typed `admin` still produced it.

These tests also guard the deploy ORDER. The server's refusal is gated OFF
until every bridge is swept, and the thing being swept is exactly the routing
below — so if these regress, the gate can never be flipped.
"""

import engram_mcp.identity as identity
from engram_mcp.identity import (
    ADMIN_FLEET,
    compute_identity,
    qualify_admin_target,
    reader_to_address,
)


def _host(monkeypatch, host="hosta"):
    monkeypatch.setattr(identity, "hostname", lambda: host)


# ------------------------------------------------------------ reply routing


def test_bare_admin_target_recovers_the_host_from_the_envelope():
    """The machine axis is already on the From line — stop discarding it."""
    assert qualify_admin_target("admin", "admin@hosta") == "admin@hosta"
    assert qualify_admin_target("admin", "admin@hostb") == "admin@hostb"
    assert qualify_admin_target("ADMIN", "admin@hosta") == "admin@hosta"


def test_the_stripping_that_caused_this_is_still_what_it_was():
    """reader_to_address is unchanged — the fix wraps it, never rewrites it.

    Deployed bridges rely on this returning the name-part (measured by
    adversarial review 2026-08-14), so it stays the wire contract.
    """
    assert reader_to_address("admin@hosta") == "admin"
    assert reader_to_address("engram-claude-12@hostc") == "engram-claude-12"
    assert reader_to_address("machine:hosta") == "machine:hosta"


def test_non_admin_addresses_pass_through_untouched():
    assert qualify_admin_target("engram", "engram@hostc") == "engram"
    assert qualify_admin_target("projbeta", "admin@hosta") == "projbeta"
    assert qualify_admin_target("administrator", "admin@hosta") == "administrator"
    assert qualify_admin_target("admin-grok", "admin@hosta") == "admin-grok"


def test_already_qualified_targets_are_not_rewritten():
    assert qualify_admin_target("admin@hostb", "admin@hosta") == "admin@hostb"
    assert qualify_admin_target(ADMIN_FLEET, "admin@hosta") == ADMIN_FLEET


def test_missing_or_hostless_sender_leaves_the_target_alone():
    """No host to recover means no host to invent.

    Guessing a box would be worse than refusing: the server's refusal tells the
    sender to name one, which is a person-fixable error. A wrong guess is a
    silently misdelivered request — the exact failure this item exists to end.
    """
    assert qualify_admin_target("admin", "") == "admin"
    assert qualify_admin_target("admin", "admin") == "admin"
    assert qualify_admin_target("admin", None) == "admin"


# --------------------------------------------------------------- listen_set


def test_admin_session_declares_the_fleet_broadcast_address(monkeypatch):
    _host(monkeypatch)
    monkeypatch.delenv(identity.INBOX_IDENTITY_ENV, raising=False)
    monkeypatch.setattr(identity, "derive_project_name", lambda _d: "admin")
    monkeypatch.setattr(identity, "resolve_inbox_identity", lambda _d: None)
    reader, listen_set = compute_identity("/whatever")
    assert reader == "admin@hosta"
    assert ADMIN_FLEET in listen_set
    # The bare role stays — the 149 messages already sent to it must remain
    # readable, and the server's refusal is about SENDING, not listening.
    assert "admin" in listen_set
    assert "machine:hosta" in listen_set
    assert "admin@hosta" in listen_set
    # SEAT-ADMIN-1: admin grows no provider lanes.
    assert "admin-claude" not in listen_set


def test_non_admin_sessions_gain_no_fleet_address(monkeypatch):
    _host(monkeypatch)
    monkeypatch.delenv(identity.INBOX_IDENTITY_ENV, raising=False)
    monkeypatch.setattr(identity, "derive_project_name", lambda _d: "projbeta")
    monkeypatch.setattr(identity, "resolve_inbox_identity", lambda _d: None)
    _, listen_set = compute_identity("/whatever")
    assert ADMIN_FLEET not in listen_set
    assert not any(a.endswith("@fleet") for a in listen_set)
