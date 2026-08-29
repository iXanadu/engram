"""memory_roster rendering — the four watcher states, as OBSERVATIONS.

ROSTER-FAREWELL-RENDER (2026-08-21): the server has returned `farewell_at`
on roster entries since FAREWELL-1 (ed5709b), but the bridge renderer only
knew three beat states, so a seat whose watcher OBSERVED the session exit
rendered as "watcher gone quiet" — indistinguishable from a busy session.
Measured on two seats across two projects the morning after it shipped.
These tests pin all four branches, because none of them had a test before.
"""

import pytest

from engram_mcp import server as srv


def _entry(identity, **kw):
    base = {
        "identity": identity,
        "project": "proj",
        "provider": "claude",
        "age_seconds": 12.0,
        "is_stale": False,
        "collision": False,
        "watcher_alive": None,
        "farewell_at": None,
    }
    base.update(kw)
    return base


async def _render(monkeypatch, entries):
    async def _noop_heartbeat(project_dir):
        return None

    async def _fake_roster(**kw):
        return {"status": "ok", "entries": entries}

    monkeypatch.setattr(srv, "_heartbeat", _noop_heartbeat)
    monkeypatch.setattr(srv._client, "roster", _fake_roster)
    return await srv.memory_roster(project="proj", project_dir="/tmp/x")


@pytest.mark.asyncio
async def test_three_beat_states_render_as_observations(monkeypatch):
    out = await _render(monkeypatch, [
        _entry("proj-claude-1", watcher_alive=True),
        _entry("proj-claude-2", watcher_alive=False),
        _entry("proj-claude-3", watcher_alive=None),
    ])
    assert "proj-claude-1" in out and "watcher beat recently" in out
    assert "proj-claude-2" in out and "watcher gone quiet" in out
    # ROSTER-BLIND-1: the None case must report what the column KNOWS — that
    # no BRIDGE-REGISTERED watcher has beaten — never the verdict "nobody is
    # listening". A client polling /memory/inbox/wait with its own token
    # registers no claim and is invisible here; rendering that as "no watcher"
    # sent three sessions to three wrong conclusions in one morning.
    assert "proj-claude-3" in out
    assert "no bridge-registered watcher" in out
    assert "external pollers invisible" in out
    # The old wording is a verdict the column cannot support. Guard against
    # anyone restoring it.
    assert "no watcher seen" not in out
    # a fresh-but-quiet seat gets the "no watcher beat" advisory; it is NOT
    # called dead (a busy agent and a dead one are both silent — MSG-8).
    assert "ADDRESSABLE, NO WATCHER BEAT: proj-claude-2" in out
    assert "EXITED" not in out


@pytest.mark.asyncio
async def test_farewell_renders_as_observed_exit_not_silence(monkeypatch):
    out = await _render(monkeypatch, [
        _entry("proj-claude-5", watcher_alive=False, is_stale=True,
               farewell_at="2026-08-21T15:53:07.123456Z"),
        _entry("proj-claude-6", watcher_alive=True),
    ])
    line = next(l for l in out.splitlines() if l.strip().startswith("proj-claude-5"))
    # the observation, with the time, on the seat's own line
    assert "watcher OBSERVED the session exit at 2026-08-21T15:53:07Z" in line
    # it OUTRANKS the beat state: not "gone quiet" on that line
    assert "watcher gone quiet" not in line
    # and the seat is called out in its own footer, as an exit, not as silence
    assert "☠ EXITED: proj-claude-5" in out
    assert "Do not hand work to these chairs" in out
    # the live seat is untouched
    assert "proj-claude-6" in out and "watcher beat recently" in out


@pytest.mark.asyncio
async def test_farewelled_seat_never_lands_in_no_watcher_beat_advisory(monkeypatch):
    # The advisory text says "a session can be doing real work with a dead
    # watcher" — the one thing an OBSERVED exit rules out. A farewelled seat
    # that is not yet stale must not be listed there.
    out = await _render(monkeypatch, [
        _entry("proj-claude-7", watcher_alive=False, is_stale=False,
               farewell_at="2026-08-21T16:00:00Z"),
    ])
    assert "☠ EXITED: proj-claude-7" in out
    assert "ADDRESSABLE, NO WATCHER BEAT" not in out


def test_short_ts_trims_iso_and_passes_odd_shapes_through():
    assert srv._short_ts("2026-08-21T15:53:07.123456+00:00") == "2026-08-21T15:53:07Z"
    assert srv._short_ts("2026-08-21T15:53:07Z") == "2026-08-21T15:53:07Z"
    # never hide the fact because of its shape
    assert srv._short_ts("yesterday-ish") == "yesterday-ish"
    assert srv._short_ts(1755790000) == "1755790000"


@pytest.mark.asyncio
async def test_certified_death_outranks_everything_and_names_the_certifier(monkeypatch):
    # Dead-shows-dead (2026-08-21): a LANE-4 certificate from the spawner is
    # the strongest exit fact — it performed the kill. It outranks a beat
    # state AND an observed farewell on the same row, prints who certified
    # and when, and lands the seat in the EXITED footer, never the
    # "no watcher beat" advisory.
    out = await _render(monkeypatch, [
        _entry("proj-grok-2", watcher_alive=False, is_stale=True,
               farewell_at="2026-08-21T17:14:50Z",
               death={"died_at": "2026-08-21T17:15:20.963246+00:00",
                      "cause": "stopped", "graceful": True,
                      "certified_by": "projalpha"}),
        _entry("proj-claude-9", watcher_alive=True),
    ])
    line = next(l for l in out.splitlines() if l.strip().startswith("proj-grok-2"))
    assert "EXITED — certified dead by projalpha at 2026-08-21T17:15:20Z" in line
    assert "OBSERVED" not in line and "gone quiet" not in line
    assert "☠ EXITED: proj-grok-2" in out
    assert "ADDRESSABLE, NO WATCHER BEAT" not in out
    assert "proj-claude-9" in out and "watcher beat recently" in out


@pytest.mark.asyncio
async def test_death_without_certifier_still_renders(monkeypatch):
    out = await _render(monkeypatch, [
        _entry("proj-codex-1", death={"died_at": "2026-08-21T10:00:00Z"}),
    ])
    assert "EXITED — certified dead by spawner at 2026-08-21T10:00:00Z" in out


# ── WATCH-RENDER-1 (2026-08-23): a beat is not ownership ────────────────────
#
# The four states above answer "did a watcher poll here". None of them
# answers "does anyone OWN this seat's wake stream", and the retired
# arm-your-own watcher beats without ever claiming — so a seat nobody was
# listening for rendered exactly like a covered one. Measured on a live
# hub-spawned Cursor seat that read "watcher beat recently" here while its
# own status line read NOT COVERED, at the same instant.


@pytest.mark.asyncio
async def test_beat_with_a_live_claim_says_it_owns_the_stream(monkeypatch):
    out = await _render(monkeypatch, [
        _entry("proj-claude-1", watcher_alive=True,
               watch={"state": "covered", "armed_by": "bridge"}),
    ])
    assert "owns the wake stream" in out
    assert "NOBODY OWNS" not in out
    assert "BEATING BUT UNOWNED" not in out


@pytest.mark.asyncio
async def test_beat_without_a_claim_is_flagged_not_reported_as_healthy(monkeypatch):
    """THE CURSOR CASE — the whole reason this exists."""
    out = await _render(monkeypatch, [
        _entry("projepsilon-cursor-2", watcher_alive=True,
               watch={"state": "unheld"}),
    ])
    assert "NOBODY OWNS its wake stream (unheld)" in out
    assert "BEATING BUT UNOWNED: projepsilon-cursor-2" in out
    # It is NOT a death verdict and must never read as one: such a session
    # may still be driven by its host, and mail queues either way.
    assert "EXITED" not in out
    assert "ADDRESSABLE, NO WATCHER BEAT" not in out


@pytest.mark.asyncio
async def test_expired_claim_is_distinct_from_never_claimed(monkeypatch):
    """`expired` (a holder went quiet) and `unheld` (none ever existed) are
    different facts — collapsing them is the absence-vs-failure confusion."""
    out = await _render(monkeypatch, [
        _entry("proj-claude-1", watcher_alive=True,
               watch={"state": "expired", "armed_by": "bridge"}),
    ])
    assert "NOBODY OWNS its wake stream (expired)" in out


@pytest.mark.asyncio
async def test_old_server_without_the_field_is_not_rendered_as_unheld(monkeypatch):
    """WIRE-1 discipline in the other direction. A pre-WATCH-RENDER-1 server
    serves no `watch` key at all. Absent means IT CANNOT ANSWER — rendering
    that as "nobody owns it" would invent a fleet-wide false alarm on every
    box that had not deployed yet, which is the same class of error this
    change exists to remove."""
    out = await _render(monkeypatch, [
        _entry("proj-claude-1", watcher_alive=True),   # no `watch` key
    ])
    assert "watcher beat recently" in out
    assert "NOBODY OWNS" not in out
    assert "BEATING BUT UNOWNED" not in out


# ---------------------------------------------------------- ADMIN-ADDR-1
#
# The directory used to print the BARE shared role and then instruct callers to
# "address an entry by its identity" — which is how senders were taught the
# form that reaches every box at once. Measured 2026-08-29: 149 of 200 messages
# in one admin inbox were on the bare role, and a session started another host's
# work from a request it could not recognise as not-its-own.


@pytest.mark.asyncio
async def test_shared_role_renders_a_box_address_not_the_bare_name(monkeypatch):
    out = await _render(monkeypatch, [
        _entry("admin", project="admin", host="hosta",
               hosts_seen=["hosta"], watcher_alive=True),
    ])
    assert "admin@hosta" in out, "the roster must offer a DM-able address"
    # The bare role must not be sitting in the identity column pretending to be
    # one. It may still appear in prose (the footer explains the rule).
    assert "  admin  " not in out
    assert "\n  admin " not in out


@pytest.mark.asyncio
async def test_other_boxes_are_named_but_not_given_this_row_freshness(monkeypatch):
    """The age belongs to the LAST beater — the others' does not.

    Printing every host in the identity column would attach one row's
    freshness to sessions that never reported it: a second confident-and-wrong
    reading of a single aggregate, which is the exact failure WATCH-RENDER-1
    and ROSTER-BLIND-1 were both about.
    """
    out = await _render(monkeypatch, [
        _entry("admin", project="admin", host="hosta",
               hosts_seen=["hosta", "hostb", "hostc"],
               age_seconds=17.0, watcher_alive=True),
    ])
    assert "admin@hosta" in out
    assert "admin@hostb" in out and "admin@hostc" in out
    assert "SHARED ROLE" in out
    # Says where the age applies and refuses to imply it covers the others.
    assert "NOT this row's" in out
    # Teaches both valid send forms.
    assert "@fleet" in out
    # Exactly one row in the identity column, not three.
    assert out.count("project=admin last spoke") == 1


@pytest.mark.asyncio
async def test_single_box_shared_role_gets_no_footer(monkeypatch):
    """No other hosts seen ⇒ nothing to disambiguate ⇒ no noise."""
    out = await _render(monkeypatch, [
        _entry("admin", project="admin", host="hosta", hosts_seen=["hosta"]),
    ])
    assert "admin@hosta" in out
    assert "SHARED ROLE" not in out


@pytest.mark.asyncio
async def test_ordinary_identities_are_untouched(monkeypatch):
    out = await _render(monkeypatch, [
        _entry("proj-claude-1", host="hosta", hosts_seen=["hosta"],
               watcher_alive=True),
    ])
    assert "proj-claude-1" in out
    assert "proj-claude-1@hosta" not in out, \
        "only SHARED roles are host-qualified; a seat already names one session"
    assert "SHARED ROLE" not in out


@pytest.mark.asyncio
async def test_shared_role_with_no_host_is_left_alone(monkeypatch):
    """No beat has carried a host — so there is no box to name.

    Rendering `admin@None` or guessing would be worse than the bare name: the
    bare name is at least honestly ambiguous.
    """
    out = await _render(monkeypatch, [
        _entry("admin", project="admin", host=None, hosts_seen=[]),
    ])
    assert "admin@" not in out
    assert "admin" in out
