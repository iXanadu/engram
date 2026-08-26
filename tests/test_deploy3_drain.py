"""DEPLOY-3: a bounce must not wait out held long-polls.

Background, measured 2026-08-26 on a spare-port rig: with a single 120s
``/memory/inbox/wait`` in flight, SIGTERM-to-exit took **116 seconds** —
uvicorn drains in-flight requests, and a long-poll is one. The deploy
script's 30s patience is therefore consumed by a perfectly healthy drain,
and it reports "still alive — investigate" on a routine restart.

The ledger's first suggested fix (size the script's wait to the long-poll
timeout) is not available: ``timeout_seconds`` is capped at 300 and chosen
by the CALLER, so there is no bound the script could be sized to. The fix
is therefore to release the waiters when we are asked to stop.
"""

import asyncio
import signal

import pytest

from server.shutdown import shutting_down, install_signal_hook


@pytest.fixture(autouse=True)
def _clear_flag():
    shutting_down.clear()
    yield
    shutting_down.clear()


@pytest.mark.asyncio
async def test_wait_returns_promptly_when_shutting_down(client):
    """A long wait must not outlive the stop signal.

    The caller asked for 120s. Once the flag is raised it must come back
    immediately — that difference is the whole defect.
    """
    async def raise_flag():
        await asyncio.sleep(0.2)
        shutting_down.set()

    asyncio.create_task(raise_flag())
    r = await asyncio.wait_for(
        client.post("/memory/inbox/wait", json={
            "listen_set": ["deploy3probe"], "timeout_seconds": 120,
        }),
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "timeout"
    assert body["waited_seconds"] < 15
    assert "restarting" in body["guidance"].lower()


@pytest.mark.asyncio
async def test_wait_still_times_out_normally_when_not_shutting_down(client):
    """The flag must not be the only way out — an ordinary short wait still
    ends on its own clock, with the ordinary guidance."""
    r = await client.post("/memory/inbox/wait", json={
        "listen_set": ["deploy3probe2"], "timeout_seconds": 1,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "timeout"
    assert "re-issue" in body["guidance"].lower()
    assert "restarting" not in body["guidance"].lower()


def test_signal_hook_chains_rather_than_replaces():
    """We must not steal uvicorn's handler.

    Ours raises the flag; uvicorn's is what actually stops the server. If
    this chain breaks, the drain gets faster and the process never exits —
    strictly worse than the bug being fixed.
    """
    called = []

    def previous(signum, frame):
        called.append(signum)

    import server.shutdown as sd

    original = signal.getsignal(signal.SIGTERM)

    async def scenario():
        # Install ours ON TOP of `previous`, then fire it while this loop is
        # still running — the hook hands the flag to the loop, so a closed
        # one proves nothing.
        signal.signal(signal.SIGTERM, previous)
        sd._installed = False
        sd.shutting_down.clear()
        install_signal_hook()

        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not previous, "hook was not installed"

        handler(signal.SIGTERM, None)
        assert called == [signal.SIGTERM], "previous handler was not chained"

        await asyncio.sleep(0)  # let call_soon_threadsafe land
        assert sd.shutting_down.is_set(), "hook did not raise the flag"

    try:
        asyncio.run(scenario())
    finally:
        signal.signal(signal.SIGTERM, original)
        sd._installed = False
        sd.shutting_down.clear()
