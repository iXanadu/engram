"""OWN-2: a listing must not print the partition where the reader expects the author.

Measured 2026-08-23 while correcting a stale `state/*` row: `memory_keys`
printed `user_id` — the PARTITION — and a reader took it for the row's writer.
Ownership (OWN-1) is by PRINCIPAL, held in `owner`, and the two disagree
exactly when it matters. So a listing read "claude-code" on a row only
`ixanadu` may write, and the refusal arrived as a 409 at the moment of the
edit — after the reader had already decided what to do.

The 409 itself is good: it names the holder. The LISTING is what misled.

class:absence-vs-failure — and note the second trap in the same field: a NULL
owner is not "author unknown", it is a legacy row the write gate deliberately
lets ANY writer through. A blank would re-create the ambiguity in a new place.
"""

import pytest

NS = "engram-test"
PROJECT = "own2-proj"


async def _cleanup(db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM memories WHERE namespace = $1 AND project = $2",
            NS, PROJECT)


async def _keys(client, **kw):
    body = {"namespace": NS, "prefix": "", "scope": "project",
            "project": PROJECT, "user_id": "*", "limit": 50}
    body.update(kw)
    resp = await client.post("/memory/keys", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_listing_carries_owner_and_custodian(client, db_pool):
    """The fields the renderer needs must actually be served."""
    try:
        resp = await client.post("/memory/set", json={
            "namespace": NS, "key": "state/thing", "value": "v",
            "scope": "project", "project": PROJECT, "expiration_days": 0})
        assert resp.status_code == 200, resp.text

        entries = (await _keys(client))["keys"]
        assert entries, "nothing listed"
        row = next(e for e in entries if e["key"] == "state/thing")
        assert "owner" in row, "owner absent — the listing still cannot name the writer"
        assert "custodian" in row
    finally:
        await _cleanup(db_pool)


@pytest.mark.asyncio
async def test_owner_is_the_principal_not_the_partition(client, db_pool):
    """The whole defect in one assertion.

    These two fields are what a reader conflates. When ownership was recorded,
    `owner` must be the PRINCIPAL — and the test must fail if someone ever
    "simplifies" it back to echoing user_id.
    """
    try:
        await client.post("/memory/set", json={
            "namespace": NS, "key": "state/owned", "value": "v",
            "scope": "project", "project": PROJECT, "expiration_days": 0})

        async with db_pool.acquire() as conn:
            actual_owner = await conn.fetchval(
                "SELECT owner FROM memories WHERE namespace=$1 AND key=$2 "
                "AND project=$3", NS, "state/owned", PROJECT)

        row = next(e for e in (await _keys(client))["keys"]
                   if e["key"] == "state/owned")
        assert row["owner"] == actual_owner, (
            "listing's owner disagrees with the column the write gate reads")
    finally:
        await _cleanup(db_pool)


@pytest.mark.asyncio
async def test_a_legacy_row_reports_null_owner_not_a_guess(client, db_pool):
    """A pre-`owner` row must come back NULL, not backfilled from user_id.

    The write gate lets a NULL-owner row through for ANY writer. If the
    listing invented an owner here, it would report a restriction that does
    not exist — the mirror image of the original bug.
    """
    try:
        await client.post("/memory/set", json={
            "namespace": NS, "key": "state/legacy", "value": "v",
            "scope": "project", "project": PROJECT, "expiration_days": 0})
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE memories SET owner = NULL WHERE namespace=$1 AND "
                "key=$2 AND project=$3", NS, "state/legacy", PROJECT)

        row = next(e for e in (await _keys(client))["keys"]
                   if e["key"] == "state/legacy")
        assert row["owner"] is None, "a legacy row was given an owner it never had"
    finally:
        await _cleanup(db_pool)
