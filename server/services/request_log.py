"""OBS-REQLOG-1 — the request trail.

Answers "which credential called what, and when". Before this existed nothing
could: an identity question had to be settled by hashing tokens instead of
reading a log, narrowing the public allowlist was a guess rather than a
measurement, and a whole session's worth of questions about whether an
external client was polling us were simply unanswerable.

What is deliberately NOT here: request bodies, and query-string VALUES. The
path is stored with its query stripped, so a token or a search term that a
client put in a URL cannot land in this table. The rows still name principals,
so retention is bounded (``request_log_retention_days``) and pruned by the
existing cleanup loop rather than kept forever.
"""
import logging

from server.db import get_pool

logger = logging.getLogger(__name__)

# High-volume, zero-information paths. Health is polled by the service manager
# and every uptime check on the fleet; /static is pinned dashboard assets. They
# would dominate the table and answer nothing anyone asks of it.
SKIP_PREFIXES = ("/health", "/static")


def should_log(path: str) -> bool:
    """False for paths whose volume would drown the signal."""
    return not path.startswith(SKIP_PREFIXES)


async def record_request(
    *,
    principal: str | None,
    auth_source: str | None,
    method: str,
    path: str,
    status: int,
    duration_ms: int,
) -> None:
    """Write one request row. Never raises — observability must not be able to
    fail a request that otherwise succeeded."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO request_log
                    (principal, auth_source, method, path, status, duration_ms)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                principal, auth_source, method, path, status, duration_ms,
            )
    except Exception:
        # Deliberately swallowed and logged, not re-raised. A failure to
        # RECORD a request must never become a failure OF that request.
        logger.exception("request_log write failed")


async def prune_request_log(retention_days: int) -> int:
    """Delete rows older than the retention window. Returns rows removed."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM request_log "
            "WHERE created_at < NOW() - ($1 || ' days')::INTERVAL",
            str(retention_days),
        )
    # asyncpg returns e.g. "DELETE 42"
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0
