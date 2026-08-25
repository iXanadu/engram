"""OBS-REQLOG-1 — the request trail, and what it deliberately does not record."""
import pytest

from server.services.request_log import (
    prune_request_log,
    record_request,
    should_log,
)


class TestSkipRules:
    def test_health_is_skipped(self):
        # Polled by the service manager and every uptime check on the fleet —
        # it would dominate the table and answer nothing anyone asks of it.
        assert should_log("/health") is False

    def test_static_is_skipped(self):
        assert should_log("/static/app.js") is False

    def test_memory_routes_are_logged(self):
        assert should_log("/memory/search") is True
        assert should_log("/admin/principals") is True
        assert should_log("/whoami") is True


@pytest.mark.asyncio
class TestRecording:
    async def test_records_a_row(self, db_pool):
        await record_request(
            principal="test-principal", auth_source="principal",
            method="POST", path="/memory/search", status=200, duration_ms=12,
        )
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM request_log WHERE principal='test-principal' "
                "ORDER BY id DESC LIMIT 1"
            )
        assert row is not None
        assert row["method"] == "POST"
        assert row["path"] == "/memory/search"
        assert row["status"] == 200
        assert row["auth_source"] == "principal"

    async def test_anonymous_request_records_null_principal(self, db_pool):
        await record_request(
            principal=None, auth_source="anonymous",
            method="GET", path="/whoami", status=401, duration_ms=3,
        )
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM request_log WHERE path='/whoami' "
                "ORDER BY id DESC LIMIT 1"
            )
        # A rejected credential is exactly the event the trail exists for —
        # it must not be dropped for lacking a principal.
        assert row is not None
        assert row["principal"] is None
        assert row["status"] == 401

    async def test_write_failure_never_raises(self, monkeypatch):
        """Observability must not be able to fail a request that succeeded."""
        async def boom():
            raise RuntimeError("pool is down")
        monkeypatch.setattr("server.services.request_log.get_pool", boom)
        # Must return normally, not raise.
        await record_request(
            principal="x", auth_source="principal",
            method="GET", path="/memory/get", status=200, duration_ms=1,
        )


@pytest.mark.asyncio
class TestRetention:
    async def test_prunes_only_rows_past_the_window(self, db_pool):
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM request_log")
            await conn.execute(
                "INSERT INTO request_log "
                "(principal, auth_source, method, path, status, duration_ms, created_at) "
                "VALUES ('old', 'principal', 'GET', '/memory/get', 200, 1, "
                "NOW() - INTERVAL '40 days')"
            )
            await conn.execute(
                "INSERT INTO request_log "
                "(principal, auth_source, method, path, status, duration_ms, created_at) "
                "VALUES ('recent', 'principal', 'GET', '/memory/get', 200, 1, "
                "NOW() - INTERVAL '2 days')"
            )
        removed = await prune_request_log(30)
        assert removed == 1
        async with db_pool.acquire() as conn:
            survivors = await conn.fetch("SELECT principal FROM request_log")
        assert [r["principal"] for r in survivors] == ["recent"]
