import pytest
from httpx import ASGITransport, AsyncClient

@pytest.mark.asyncio
async def test_middleware_sets_via_public_from_header(services, db_pool):
    from server.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.get("/whoami", headers={"x-engram-public": "1"})
        await c.get("/whoami")
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT via_public FROM request_log WHERE path='/whoami' ORDER BY id DESC LIMIT 2")
    assert [r["via_public"] for r in rows] == [False, True]
