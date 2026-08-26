"""MEM-9: "already superseded" must not wear the vocabulary of "never existed".

The incident (2026-08-22 18:30Z): two seats retried a supersede the store had
ALREADY performed — stamped, attributed, replacement set. Both got
``404 no live row … within your readable namespaces`` and both read it as
"permission refused / row not found". The work was done and the answer said it
was not, so they went looking for a permissions problem that did not exist.

class:absence-vs-failure — an answer accurate about one thing ("there is no
LIVE row") and read as meaning another ("your row is missing or you may not
touch it"), silent about the difference.
"""

import pytest

NS = "engram-test"
PROJECT = "mem9-proj"
KEY = "decision/mem9-thing"


async def _seed(client, user_id="grok"):
    resp = await client.post("/memory/set", json={
        "namespace": NS, "key": KEY, "value": "the original claim",
        "scope": "project", "user_id": user_id, "project": PROJECT,
        "expiration_days": 0,
    })
    assert resp.status_code == 200, resp.text


async def _supersede(client, key=KEY, user_id="grok", replacement=None):
    body = {
        "namespace": NS, "key": key, "project": PROJECT,
        "target_user_id": user_id,
        "reason": "superseded by a later measurement",
    }
    if replacement:
        body["replacement_key"] = replacement
    return await client.post("/memory/supersede", json=body)


async def _cleanup(client, db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM memories WHERE namespace = $1 AND project = $2",
            NS, PROJECT)


@pytest.mark.asyncio
async def test_second_supersede_says_already_done_not_missing(client, db_pool):
    """The defect, exactly: retry the operation and read the answer."""
    try:
        await _seed(client)
        first = await _supersede(client, replacement="correction/newer")
        assert first.status_code == 200, first.text

        second = await _supersede(client, replacement="correction/newer")
        assert second.status_code == 404
        detail = second.json()["detail"]

        # It must AFFIRM what happened...
        assert "ALREADY superseded" in detail
        assert "has already happened" in detail
        # ...name who and what replaced it, so the caller can verify it...
        assert "correction/newer" in detail
        # ...and explicitly disclaim the two readings that cost two seats an
        # evening. This is the whole point of the fix.
        assert "not a permission refusal" in detail
        assert "not a missing row" in detail
    finally:
        await _cleanup(client, db_pool)


@pytest.mark.asyncio
async def test_a_genuine_miss_still_reads_as_a_miss(client, db_pool):
    """The other half — the honest branch must not swallow real misses.

    If everything started reporting "already superseded", the fix would have
    replaced one misleading answer with a worse one.
    """
    try:
        resp = await _supersede(client, key="decision/never-existed-at-all")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "no live row" in detail
        assert "ALREADY superseded" not in detail
    finally:
        await _cleanup(client, db_pool)


@pytest.mark.asyncio
async def test_wrong_writer_is_a_miss_not_an_already_done(client, db_pool):
    """A live row under a DIFFERENT writer must not be reported as retired.

    The lookup keys on the same fields as the update; if it were looser it
    would cheerfully report someone else's superseded row as yours.
    """
    try:
        await _seed(client, user_id="grok")
        first = await _supersede(client, user_id="grok")
        assert first.status_code == 200

        # same key, different writer — nothing of theirs was ever superseded
        resp = await _supersede(client, user_id="somebody-else")
        assert resp.status_code == 404
        assert "ALREADY superseded" not in resp.json()["detail"]
    finally:
        await _cleanup(client, db_pool)


@pytest.mark.asyncio
async def test_stamp_survives_a_missing_replacement_key(client, db_pool):
    """Not every supersede names a replacement; the branch must still fire."""
    try:
        await _seed(client)
        assert (await _supersede(client)).status_code == 200
        second = await _supersede(client)
        assert second.status_code == 404
        assert "ALREADY superseded" in second.json()["detail"]
    finally:
        await _cleanup(client, db_pool)
