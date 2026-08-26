"""The owner-backfill target is FUNCTIONAL, and a scrub once treated it as prose.

2026-08-26: a public-repo cleanup rewrote every internal name in the tree.
One of them was not a name in prose — it was the literal in

    UPDATE memories SET owner = '<owner principal>'

so the backfill was pointed at a principal that does not exist. Had it
deployed, it would have stamped ownership of the legacy corpus to a
non-existent owner and locked the real one out behind the OWN-1 write gate,
recoverable only from a backup. It was caught before deploy, and the full
512-test suite did NOT catch it — hence this file.

The literal now comes from settings and is validated, so the tree carries no
hardcoded identity AND a rename cannot silently corrupt ownership.
"""

import re

import pytest

from server.config import settings
from server.db import MIGRATE_SQL, _render_migrate_sql

BACKFILL = re.compile(r"UPDATE memories SET owner = '([^']+)'")


def test_placeholder_never_survives_rendering(monkeypatch):
    """Whatever happens, the template token must not reach the database."""
    for value in ("someowner", "", "not a valid name!"):
        monkeypatch.setattr(settings, "owner_principal_name", value)
        assert "__OWNER_PRINCIPAL__" not in _render_migrate_sql()


def test_configured_owner_is_substituted(monkeypatch):
    monkeypatch.setattr(settings, "owner_principal_name", "someowner")
    m = BACKFILL.search(_render_migrate_sql())
    assert m and m.group(1) == "someowner"


def test_no_owner_configured_removes_the_backfill_entirely(monkeypatch):
    """Doing nothing is recoverable; stamping a guess is not.

    An unconfigured deployment must not backfill ownership to some default —
    that is the failure this test exists to prevent.
    """
    monkeypatch.setattr(settings, "owner_principal_name", "")
    out = _render_migrate_sql()
    assert BACKFILL.search(out) is None
    # ...and the REST of the migration must survive the surgery.
    assert "ADD COLUMN IF NOT EXISTS via_public" in out
    assert "ADD COLUMN IF NOT EXISTS machine" in out


@pytest.mark.parametrize("hostile", [
    "bob'; DROP TABLE memories; --",
    "a' OR '1'='1",
    "name with spaces",
    "x" * 65,
])
def test_injection_shaped_names_are_refused_not_interpolated(monkeypatch, hostile):
    """The name cannot be a bind parameter (MIGRATE_SQL runs as one block),
    so it is substituted — which makes it an injection site unless validated.
    """
    monkeypatch.setattr(settings, "owner_principal_name", hostile)
    out = _render_migrate_sql()
    assert hostile not in out
    assert BACKFILL.search(out) is None


def test_the_template_still_contains_the_backfill(monkeypatch):
    """Guard against the opposite failure: if someone deletes the statement
    from MIGRATE_SQL, every test above passes vacuously.
    """
    assert "__OWNER_PRINCIPAL__" in MIGRATE_SQL
