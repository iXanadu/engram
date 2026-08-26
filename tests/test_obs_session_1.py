"""OBS-SESSION-1: the request trail records WHICH BOX, not only which credential.

Measured 2026-08-26: every agent on the fleet authenticates as the same
principal, so `principal` alone could not separate this machine's traffic from
the other four. Answering "what does one session cost" needed local `ps` plus
arithmetic — and local `ps` cannot see the remote boxes at all, so the number
it produced was a fleet sum that did not announce itself.

Both values ride provenance headers the bridge already sends, so this costs no
client change and no fleet sweep. They are RECORDED, NOT TRUSTED: a client can
set them, so they answer "which box says it called".
"""
import pytest

from server.request_logging import _clip


class TestClip:
    def test_none_and_empty_stay_none(self):
        """A blank must not become an empty string — "recorded nothing" and
        "recorded a blank" have to stay distinguishable in the table."""
        assert _clip(None) is None
        assert _clip("") is None
        assert _clip("   ") is None

    def test_ordinary_values_pass_through_trimmed(self):
        assert _clip("hosta") == "hosta"
        assert _clip("  engram  ") == "engram"

    def test_hostile_length_is_bounded(self):
        """Client-supplied and unbounded is a free write amplifier."""
        assert len(_clip("x" * 5000)) == 64


@pytest.mark.asyncio
async def test_columns_exist_and_a_request_records_them(client, db_pool):
    """End-to-end through the real middleware, not a unit call.

    The middleware is registered outermost and reads the headers off the live
    request, so a test that called record_request directly would prove the
    writer works and say nothing about whether anything reaches it.
    """
    async with db_pool.acquire() as conn:
        cols = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='request_log'")}
    assert {"machine", "project"} <= cols, f"columns missing: {cols}"

    await client.get("/whoami", headers={
        "X-Engram-Machine": "obs-session-probe",
        "X-Engram-Project": "obs-session-project",
    })

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT machine, project FROM request_log "
            "WHERE machine = $1 ORDER BY created_at DESC LIMIT 1",
            "obs-session-probe")
    assert row is not None, "the request was not recorded at all"
    assert row["machine"] == "obs-session-probe"
    assert row["project"] == "obs-session-project"


@pytest.mark.asyncio
async def test_a_request_without_the_headers_still_records(client, db_pool):
    """Absence must stay legible as absence.

    A caller that sends no provenance (curl, an external client) must still
    produce a row — with NULLs, not with a crash and not with empty strings.
    """
    await client.get("/whoami")
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT machine, project FROM request_log "
            "WHERE path = '/whoami' AND machine IS NULL "
            "ORDER BY created_at DESC LIMIT 1")
    assert row is not None, "unheadered request produced no row"
    assert row["machine"] is None and row["project"] is None


@pytest.mark.asyncio
async def test_migration_is_idempotent_on_an_existing_table(db_pool):
    """The upgrade path, not the fresh-create path.

    An earlier index in this project shipped in the wrong block and only broke
    on databases that already existed — fresh creates hid it. Run MIGRATE_SQL a
    second time against the live schema and require it to be a no-op.
    """
    from server.db import MIGRATE_SQL
    async with db_pool.acquire() as conn:
        await conn.execute(MIGRATE_SQL)
        await conn.execute(MIGRATE_SQL)
        cols = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='request_log'")}
    assert {"machine", "project"} <= cols
