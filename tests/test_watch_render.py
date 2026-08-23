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


# ── the guard on the batching, and a guard on the guard ─────────────────────
#
# The first version of this counted `fetch` calls whose SQL text contained the
# literal `watch/%`, with the pool swapped at memory_service.get_pool. Peer
# audit (projepsilon-claude-3, 2026-08-23) killed it, correctly, and the three
# holes are worth keeping written down because each one is invisible:
#
#   (a) The natural N+1 is `WHERE key = $1` with `watch/<seat>` passed as a
#       PARAMETER — its SQL text never contains `watch/%`, so one batched
#       query plus forty per-seat lookups still asserted len == 1 and passed.
#   (b) Only `fetch` was wrapped. A single-row lookup is most naturally
#       `fetchrow`/`fetchval`, which `__getattr__` passed straight through,
#       uncounted.
#   (c) `watch_claim` does its own `from server.db import get_pool`, a
#       separate binding the patch never touched — so that path acquired a
#       real, uninstrumented pool. Not merely uncounted queries: an uncounted
#       POOL.
#
# So: count every method that takes a query string, match on the ARGS as well
# as the SQL, and patch the accessor in every module that could route a watch
# read. Then prove the instrument works by pointing it at a deliberate N+1 —
# a guard nobody has watched fail is not a guard.

import server.services.memory_service as _ms
import server.services.session_registry as _sr
import server.services.watch_claim as _wc
from server.services.watch_claim import watch_status

_QUERY_METHODS = ("fetch", "fetchrow", "fetchval", "fetchmany", "execute")


def _is_watch_query(sql: str, args: tuple) -> bool:
    """Does this call read the watch rows, in EITHER shape?

    Batched: the SQL carries `scope = $2` with WATCH_SCOPE bound, and the
    literal `watch/%`. Per-seat: the SQL is `key = $1` and the discriminator
    is entirely in the ARGUMENT `watch/<seat>`. Matching only the first is
    how the original test managed to be green against the very thing it
    existed to forbid.
    """
    if "watch" in (sql or "").lower():
        return True
    return any(isinstance(a, str) and a.startswith("watch/") for a in args)


class _Counter:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    @property
    def n(self) -> int:
        return len(self.calls)


def _instrument(monkeypatch, real_pool) -> _Counter:
    counter = _Counter()

    class _Conn:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            inner_attr = getattr(self._inner, name)
            if name not in _QUERY_METHODS:
                return inner_attr

            async def _wrapped(sql, *args, **kw):
                if _is_watch_query(sql, args):
                    counter.calls.append((sql, args))
                return await inner_attr(sql, *args, **kw)

            return _wrapped

    class _Acquire:
        def __init__(self):
            self._ctx = real_pool.acquire()

        async def __aenter__(self):
            return _Conn(await self._ctx.__aenter__())

        async def __aexit__(self, *a):
            return await self._ctx.__aexit__(*a)

    class _Pool:
        def acquire(self, *a, **k):
            return _Acquire()

        def __getattr__(self, name):
            return getattr(real_pool, name)

    async def _fake_get_pool():
        return _Pool()

    # asyncpg's Pool.acquire is read-only, so the swap happens at the
    # accessor — in EVERY module that binds its own reference to it.
    for mod in (_ms, _sr, _wc):
        monkeypatch.setattr(mod, "get_pool", _fake_get_pool)
    return counter


@pytest.mark.asyncio
async def test_the_counter_itself_catches_an_n_plus_1(services, monkeypatch):
    """THE GUARD ON THE GUARD. Point the instrument at the exact
    implementation the batching exists to forbid — watch_status() once per
    seat — and confirm it SEES it. Without this, a silently-blind counter
    makes the two tests below permanently green and permanently worthless,
    which is precisely what the audit found."""
    try:
        seats = [f"{PROJECT}-cursor-{i}" for i in range(3)]
        for s in seats:
            await _beating_seat(s)
        real_pool = await get_pool()
        counter = _instrument(monkeypatch, real_pool)
        for s in seats:                       # the N+1, deliberately
            await watch_status(s)
        assert counter.n == 3, (
            f"instrument is blind: saw {counter.n} watch reads across 3 "
            f"per-seat watch_status() calls"
        )
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_roster_makes_one_watch_query_not_one_per_seat(services, monkeypatch):
    try:
        for i in range(3):
            await _beating_seat(f"{PROJECT}-cursor-{i}")
        real_pool = await get_pool()
        counter = _instrument(monkeypatch, real_pool)
        await roster_list(project=PROJECT, include_done=True)
        assert counter.n == 1, (
            f"expected ONE batched watch read for 3 seats, saw {counter.n}: "
            f"{[c[0][:80] for c in counter.calls]}"
        )
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_register_makes_one_watch_query_not_one_per_seat(services, monkeypatch):
    """The register is hit less often than the roster but has the same shape,
    and the two must not drift — the whole point of this change is that the
    two surfaces stop disagreeing."""
    try:
        for i in range(3):
            seat = f"{PROJECT}-cursor-{i}"
            await _beating_seat(seat)
            await seat_claim(
                project=PROJECT, provider="cursor",
                session_key=f"cursor-{PROJECT}-{i}", preferred_seat=seat,
            )
        real_pool = await get_pool()
        counter = _instrument(monkeypatch, real_pool)
        await address_register(project=PROJECT)
        assert counter.n == 1, (
            f"expected ONE batched watch read, saw {counter.n}: "
            f"{[c[0][:80] for c in counter.calls]}"
        )
    finally:
        await _cleanup()
