"""DEPLOY-3: a process-wide "we are stopping" flag that long-polls can see.

Why this exists rather than a lifespan hook: uvicorn drains in-flight
requests BEFORE it runs lifespan shutdown, so anything set there fires too
late to release a held long-poll — the very connection being waited on.
The flag is therefore raised from the SIGNAL, ahead of the drain.

Measured 2026-08-26 (scripts rig, spare port): with one 120s
``/memory/inbox/wait`` held, SIGTERM-to-exit took **116s** — the drain lasts
as long as the client's remaining timeout, and `timeout_seconds` is capped
at 300, not at the 30s default. So a deploy script cannot be "sized to the
long-poll timeout": the bound is chosen by the caller, not by us.
"""

import asyncio
import signal

# Not bound to a loop at import time (safe since CPython 3.10).
shutting_down = asyncio.Event()

_installed = False


def install_signal_hook() -> None:
    """Raise ``shutting_down`` on SIGTERM/SIGINT, then defer to uvicorn.

    We deliberately chain rather than replace: uvicorn's own handler is what
    actually stops the server. Ours only unblocks the waiters first, so the
    drain it then performs has nothing left to wait for.
    """
    global _installed
    if _installed:
        return
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(sig)

        def _handler(signum, frame, _previous=previous):
            # Thread-safe: a signal handler runs between bytecodes and must
            # not touch loop internals directly.
            loop.call_soon_threadsafe(shutting_down.set)
            if callable(_previous):
                _previous(signum, frame)

        try:
            signal.signal(sig, _handler)
        except ValueError:
            # Not the main thread (tests, embedded use) — the flag can still
            # be set manually; nothing else here is load-bearing.
            pass
    _installed = True
