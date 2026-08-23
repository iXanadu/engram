"""ALLOC-LIVENESS-1: deleting a seat row must not delete the liveness ladder.

THE DEFECT. `allocation_decision`'s no-row branch parked only on `holds_mail`
and otherwise returned FREE. `live-holder`, `grace-window` and
`presence-fresh` all sit BELOW it and are unreachable without a row — so the
ladder was not *degraded* when a row was deleted, it was BYPASSED. Nothing had
ever deleted a live session's row, so the hole was invisible until a consumer
shipped a release that inferred death from a missing file it looked for on the
wrong machine.

THE INVERSION, which is why this is worth fixing on its own merits: with the
row gone the only surviving lock was open mail — so protection was strongest
for a session BEHIND on its inbox and absent for one drained to zero, which is
exactly what the wrapup rules instruct every agent to do.

THE SHAPE. Certainty is what decides, and only the caller knows how certain it
was, so `seat_release` takes typed evidence. performed/observed stamp
`released_at` and the name is genuinely free (the tight-number promise this
path has always made). `inferred` frees the row but leaves the guard armed.

An earlier draft stamped UNCONDITIONALLY. That was worse than nothing: every
release goes through one function, so wrongful releases would have stamped too
and `live-no-row` could never have fired — a rung that exists and is
unreachable. Caught in review before it was written.
"""

import pytest

from server.services.memory_service import (
    PRESENCE_NAMESPACE,
    get_pool,
    presence_update,
)
from server.services.session_registry import (
    allocation_decision,
    seat_claim,
    seat_release,
)

PROJECT = "allocliveness"


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


async def _drop_seat_row(seat: str) -> None:
    """Delete the row WITHOUT going through seat_release — models a third
    party that decided this session was dead."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM memories WHERE namespace = $1 AND scope = 'seat' "
            "AND project = $2 AND key = $3",
            PRESENCE_NAMESPACE, PROJECT, f"seat/{seat}",
        )


# ── the ladder in isolation ─────────────────────────────────────────────────

def test_no_row_branch_parks_on_liveness():
    d = allocation_decision(root=False, lane=False, age=None,
                            holds_mail=False, presence_fresh=False,
                            live_at_address=True)
    assert d["would_skip"] is True
    assert d["reason"] == "live-no-row"


def test_live_no_row_is_distinct_from_live_holder():
    """Not folded together on purpose: `live-holder` is ordinary allocation
    against a running session, `live-no-row` can only happen after a release
    that was wrong — so it must be findable in a log."""
    with_row = allocation_decision(root=False, lane=False, age=1.0,
                                   holds_mail=False, presence_fresh=False)
    assert with_row["reason"] == "live-holder"
    no_row = allocation_decision(root=False, lane=False, age=None,
                                 holds_mail=False, presence_fresh=False,
                                 live_at_address=True)
    assert no_row["reason"] == "live-no-row"


def test_mail_still_parks_before_liveness():
    """Ordering is load-bearing: a name holding mail parks as `mail-parked`
    whatever its liveness, so the R8 reason a caller reads does not change
    meaning under this feature."""
    d = allocation_decision(root=False, lane=False, age=None,
                            holds_mail=True, presence_fresh=False,
                            live_at_address=True)
    assert d["reason"] == "mail-parked"


def test_default_keeps_old_behaviour():
    """The parameter defaults False, so every existing caller and the whole
    shipped test suite mean exactly what they meant before."""
    d = allocation_decision(root=False, lane=False, age=None,
                            holds_mail=False, presence_fresh=False)
    assert d["would_skip"] is False


# ── end to end, against the store ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_third_party_deletion_of_a_live_row_does_not_free_the_name(services):
    """ACCEPTANCE 1. A live session with a DRAINED inbox — the case that had
    no protection at all — keeps its address when something deletes its row.
    """
    try:
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-live-1")
        seat = granted["seat"]
        await presence_update(identity=seat, project=PROJECT, state="running",
                              provider="cursor", session_nonce="n1",
                              host="hosta")
        await _drop_seat_row(seat)          # the wrongful release

        other = await seat_claim(project=PROJECT, provider="cursor",
                                 session_key="cursor-stranger-2",
                                 preferred_seat=seat)
        assert other["seat"] != seat, (
            f"a stranger was granted {seat} while its holder was breathing"
        )
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_graceful_release_still_hands_back_the_tight_number(services):
    """THE REGRESSION THIS FEATURE NEARLY SHIPPED, and the reason evidence is
    typed at all.

    `seat_release` promises in its own docstring that an explicit release
    "returns the ordinal immediately so the next session gets a tight number".
    A naive liveness check breaks that: the presence row stays fresh for the
    whole window after a clean exit, so the successor would be refused and
    bumped to the next ordinal — manufacturing the churn this work exists to
    remove, on every clean restart.
    """
    try:
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-graceful-1")
        seat = granted["seat"]
        await presence_update(identity=seat, project=PROJECT, state="running",
                              provider="cursor", session_nonce="n1",
                              host="hosta")
        released = await seat_release("cursor-graceful-1", PROJECT,
                                      evidence="performed")
        assert released == seat

        successor = await seat_claim(project=PROJECT, provider="cursor",
                                     session_key="cursor-graceful-2",
                                     preferred_seat=seat)
        assert successor["seat"] == seat, (
            "a clean release must return the tight number, not bump an ordinal"
        )
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_inferred_release_over_a_live_address_is_refused(services):
    """ACCEPTANCE 6. The distinction the whole design turns on: the same
    DELETE, two evidences, two outcomes."""
    try:
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-inferred-1")
        seat = granted["seat"]
        await presence_update(identity=seat, project=PROJECT, state="running",
                              provider="cursor", session_nonce="n1",
                              host="hosta")
        await seat_release("cursor-inferred-1", PROJECT, evidence="inferred")

        successor = await seat_claim(project=PROJECT, provider="cursor",
                                     session_key="cursor-stranger-3",
                                     preferred_seat=seat)
        assert successor["seat"] != seat, (
            "an INFERRED release must not hand a breathing address away"
        )
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_unknown_evidence_takes_the_guarded_reading(services):
    """Warn, never reject — a bad value must not fail a shutdown path — but
    the fallback is the CONSERVATIVE reading, not the permissive one."""
    try:
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-typo-1")
        seat = granted["seat"]
        await presence_update(identity=seat, project=PROJECT, state="running",
                              provider="cursor", session_nonce="n1",
                              host="hosta")
        await seat_release("cursor-typo-1", PROJECT, evidence="perfomed")

        successor = await seat_claim(project=PROJECT, provider="cursor",
                                     session_key="cursor-stranger-4",
                                     preferred_seat=seat)
        assert successor["seat"] != seat
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_a_beat_after_the_stamp_wins(services):
    """A released name whose session KEPT BEATING reads live again, because
    something is demonstrably answering there. The stamp is evidence about a
    moment, not a permanent verdict."""
    try:
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-zombie-1")
        seat = granted["seat"]
        await presence_update(identity=seat, project=PROJECT, state="running",
                              provider="cursor", session_nonce="n1",
                              host="hosta")
        await seat_release("cursor-zombie-1", PROJECT, evidence="performed")
        # ... and it is still alive after all
        await presence_update(identity=seat, project=PROJECT, state="running",
                              provider="cursor", session_nonce="n1",
                              host="hosta")

        successor = await seat_claim(project=PROJECT, provider="cursor",
                                     session_key="cursor-stranger-5",
                                     preferred_seat=seat)
        assert successor["seat"] != seat
    finally:
        await _cleanup()


# ── the flaw the full suite found, pinned ───────────────────────────────────
#
# The first cut counted ANY fresh heartbeat as "someone is here". A session
# that beats presence at its declared name BEFORE its seat is granted would
# therefore have been refused its own address and pushed to an ordinal —
# locked out of the name it was actively answering to. Found by an unrelated
# existing test failing, not by reasoning about it.


@pytest.mark.asyncio
async def test_a_session_is_not_locked_out_of_its_own_address(services):
    """Beat first, claim second, same session. It must get its own name."""
    try:
        await presence_update(identity=f"{PROJECT}-cursor-2", project=PROJECT,
                              state="running", provider="cursor",
                              session_nonce="mine", host="hosta")
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-self-1",
                                   preferred_seat=f"{PROJECT}-cursor-2",
                                   session_nonce="mine")
        assert granted["seat"] == f"{PROJECT}-cursor-2", (
            "a session was refused the address it is itself heartbeating at"
        )
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_a_different_live_nonce_still_parks_the_name(services):
    """The other half of the same rule — exclusion must be the claimant's own
    nonce, not 'any nonce', or the guard is switched off entirely."""
    try:
        await presence_update(identity=f"{PROJECT}-cursor-2", project=PROJECT,
                              state="running", provider="cursor",
                              session_nonce="someone-else", host="hosta")
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-stranger-9",
                                   preferred_seat=f"{PROJECT}-cursor-2",
                                   session_nonce="mine")
        assert granted["seat"] != f"{PROJECT}-cursor-2", (
            "a stranger took an address another live session is answering at"
        )
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_absent_evidence_is_logged_loudly(services, caplog):
    """The compatibility default is a deliberate trade, and peer audit's
    condition for accepting it: make the gap GREPPABLE.

    Defaulting to `performed` means an un-migrated caller's release carries no
    liveness guard — which is the silent class of failure. A warning naming
    the session is what turns "somewhere out there a caller is unguarded" into
    something you can find, and it is the signal that says when the default
    can finally be removed.
    """
    import logging
    try:
        granted = await seat_claim(project=PROJECT, provider="cursor",
                                   session_key="cursor-quiet-1")
        with caplog.at_level(logging.WARNING,
                             logger="server.services.session_registry"):
            await seat_release("cursor-quiet-1", PROJECT)     # no evidence
        assert "seat_release_no_evidence" in caplog.text
        assert "cursor-quiet-1" in caplog.text
        assert granted["seat"]
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_declared_evidence_is_not_nagged_about(services, caplog):
    """A caller that HAS migrated must not be warned at it — otherwise the
    signal drowns in the noise it was added to surface."""
    import logging
    try:
        await seat_claim(project=PROJECT, provider="cursor",
                         session_key="cursor-loud-1")
        with caplog.at_level(logging.WARNING,
                             logger="server.services.session_registry"):
            await seat_release("cursor-loud-1", PROJECT, evidence="performed")
        assert "seat_release_no_evidence" not in caplog.text
    finally:
        await _cleanup()
