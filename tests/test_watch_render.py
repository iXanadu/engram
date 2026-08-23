"""WATCH-RENDER-1 (2026-08-23): a BEAT is not OWNERSHIP, and both surfaces say so.

Background, measured rather than reasoned. A live hub-spawned Cursor session
(seat `projepsilon-cursor-2`) was armed the RETIRED way — a watcher started
with `--follow --project-dir`, no `--claim`. That watcher BEATS, so
`presence_watcher_beat` fired and `/memory/roster` rendered
"watcher beat recently". Meanwhile the session's own bridge had spawned the
modern claiming watcher, which sat blocked waiting for a FIFO consumer that
never attached — so no claim was ever taken and the session's own
`memory_status` line read NOT COVERED. Same seat, same instant, two of our
own health surfaces giving opposite confident answers. Two agents read the
two screens and reached opposite conclusions about that seat inside twenty
minutes; one of them nearly published a correction of the other.

`watcher_alive` answers "did some watcher poll here". It cannot answer "does
anyone own this seat's wake stream", and the roster had no field that could.
These tests pin the missing fact onto both surfaces — the roster agents are
told to consult, and the address register the owner reads — in the same
three-valued vocabulary `watch_status` already served: covered / expired /
unheld.

`unheld` is NEVER a death verdict: a session may legitimately run unheld (the
store can be unreachable when its watcher arms — kill K3), and it may still be
reachable by a host that drives its turns. The renderer's job is to stop the
beat being read as coverage, not to declare anybody deaf.
"""

from datetime import datetime, timedelta, timezone

import pytest

from server.services.memory_service import (
    PRESENCE_NAMESPACE,
    WATCH_EXPIRY_SECONDS,
    WATCH_SCOPE,
    WATCH_USER_ID,
    get_pool,
    presence_update,
    presence_watcher_beat,
    roster_list,
)
from server.services.session_registry import address_register, seat_claim
from server.services.watch_claim import mint_nonce, watch_claim

PROJECT = "watchrender"
BEATER = "watchrender-cursor-2"


async def _cleanup():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM memories WHERE scope = 'presence' AND user_id = $1",
            PROJECT,
        )
        await conn.execute(
            "DELETE FROM memories WHERE namespace = $1 AND scope = 'seat' "
            "AND project = $2",
            PRESENCE_NAMESPACE, PROJECT,
        )
        await conn.execute(
            "DELETE FROM memories WHERE namespace = $1 AND scope = $2 "
            "AND user_id = $3 AND key LIKE $4",
            PRESENCE_NAMESPACE, WATCH_SCOPE, WATCH_USER_ID,
            f"watch/{PROJECT}%",
        )


async def _roster_entry(identity: str) -> dict:
    entries = await roster_list(project=PROJECT, include_done=True)
    matches = [e for e in entries if e["identity"] == identity]
    assert matches, f"{identity} not on roster"
    return matches[0]


async def _beating_seat(identity: str = BEATER) -> None:
    """A session that is alive and whose watcher beats — and nothing more.

    This is the retired-arm shape exactly: a beat with no claim behind it.
    """
    await presence_update(
        identity=identity, project=PROJECT, state="running",
        provider="cursor", session_nonce="n1", host="hosta",
    )
    assert await presence_watcher_beat(identity, PROJECT)


async def _age_the_claim(seat: str, seconds: int) -> None:
    """Backdate a claim's last_beat so it falls outside the expiry window."""
    pool = await get_pool()
    stale = (datetime.now(timezone.utc)
             - timedelta(seconds=seconds)).isoformat()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE memories
               SET metadata = jsonb_set(metadata, '{last_beat}', to_jsonb($5::text))
             WHERE namespace = $1 AND scope = $2 AND user_id = $3 AND key = $4
            """,
            PRESENCE_NAMESPACE, WATCH_SCOPE, WATCH_USER_ID,
            f"watch/{seat}", stale,
        )


# ── the defect itself ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_beating_watcher_without_a_claim_reads_unheld(services):
    """THE CURSOR CASE. Beat present, claim absent — and the roster says so.

    Before this change the entry carried `watcher_alive=True` and nothing
    else, so this seat was indistinguishable from a covered one.
    """
    try:
        await _beating_seat()
        e = await _roster_entry(BEATER)
        assert e["watcher_alive"] is True, "precondition: the beat is real"
        assert e["watch"]["state"] == "unheld"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_claimed_watch_reads_covered(services):
    try:
        await _beating_seat()
        verdict = await watch_claim(
            seat=BEATER, nonce=mint_nonce(), armed_by="bridge",
            project_dir=f"/tmp/{PROJECT}", listen_set=[BEATER, PROJECT],
        )
        assert verdict["verdict"] == "granted", verdict
        e = await _roster_entry(BEATER)
        assert e["watcher_alive"] is True
        assert e["watch"]["state"] == "covered"
        # Provenance rides along — never authority, but a reader debugging a
        # split like the Cursor one needs to know WHICH arm took the claim.
        assert e["watch"]["armed_by"] == "bridge"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_claim_gone_silent_reads_expired_not_unheld(services):
    """`expired` and `unheld` are different facts and must not collapse.

    expired = a holder existed and went quiet (something WAS listening).
    unheld  = no claim was ever taken. Collapsing them would erase the
    distinction between "the watcher died" and "nothing ever arrived",
    which is the same absence-vs-failure confusion this whole area keeps
    producing.
    """
    try:
        await _beating_seat()
        await watch_claim(
            seat=BEATER, nonce=mint_nonce(), armed_by="bridge",
            project_dir=f"/tmp/{PROJECT}", listen_set=[BEATER, PROJECT],
        )
        await _age_the_claim(BEATER, WATCH_EXPIRY_SECONDS + 60)
        e = await _roster_entry(BEATER)
        assert e["watch"]["state"] == "expired"
    finally:
        await _cleanup()


# ── the register, the owner's surface ────────────────────────────────────────

@pytest.mark.asyncio
async def test_address_register_carries_the_same_fact(services):
    """The two surfaces must not disagree — that is the whole bug."""
    try:
        await _beating_seat()
        await seat_claim(
            project=PROJECT, provider="cursor",
            session_key=f"cursor-{PROJECT}-1", preferred_seat=BEATER,
        )
        entries = await address_register(project=PROJECT)
        rows = [e for e in entries if e["address"] == BEATER]
        assert rows, f"{BEATER} not in register"
        assert rows[0]["watch"]["state"] == "unheld"

        await watch_claim(
            seat=BEATER, nonce=mint_nonce(), armed_by="bridge",
            project_dir=f"/tmp/{PROJECT}", listen_set=[BEATER, PROJECT],
        )
        entries = await address_register(project=PROJECT)
        rows = [e for e in entries if e["address"] == BEATER]
        assert rows[0]["watch"]["state"] == "covered"
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_one_query_not_one_per_seat(services):
    """The claim state is batched. A per-seat watch_status() call would turn
    a 40-seat roster into 40 extra round trips on the surface agents hit at
    every startup — the reason the register batches mail and deaths too."""
    try:
        for i in range(3):
            await _beating_seat(f"{PROJECT}-cursor-{i}")
        import server.services.memory_service as ms

        real_pool = await get_pool()
        seen: list[str] = []

        class _CountingConn:
            def __init__(self, inner):
                self._inner = inner

            async def fetch(self, q, *a):
                seen.append(q)
                return await self._inner.fetch(q, *a)

            def __getattr__(self, n):
                return getattr(self._inner, n)

        class _Acquire:
            def __init__(self):
                self._ctx = real_pool.acquire()

            async def __aenter__(self):
                return _CountingConn(await self._ctx.__aenter__())

            async def __aexit__(self, *a):
                return await self._ctx.__aexit__(*a)

        class _CountingPool:
            def acquire(self, *a, **k):
                return _Acquire()

            def __getattr__(self, n):
                return getattr(real_pool, n)

        # asyncpg's Pool.acquire is read-only, so the swap has to happen one
        # level up, at the accessor roster_list actually calls.
        real_get_pool = ms.get_pool

        async def _fake_get_pool():
            return _CountingPool()

        ms.get_pool = _fake_get_pool
        try:
            await roster_list(project=PROJECT, include_done=True)
        finally:
            ms.get_pool = real_get_pool
        watch_queries = [q for q in seen if "watch/%" in q]
        assert len(watch_queries) == 1, (
            f"expected ONE batched watch query, saw {len(watch_queries)}"
        )
    finally:
        await _cleanup()
