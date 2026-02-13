import asyncio
import logging

from server.config import settings
from server.services.admin_service import cleanup_expired

logger = logging.getLogger(__name__)


async def expiration_cleanup_loop() -> None:
    interval_seconds = settings.cleanup_interval_hours * 3600
    logger.info(
        "Expiration cleanup task started "
        f"(interval={settings.cleanup_interval_hours}h, batch={settings.cleanup_batch_size})"
    )
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                deleted = await cleanup_expired(batch_size=settings.cleanup_batch_size)
                if deleted:
                    logger.info(f"Scheduled cleanup removed {deleted} expired memories")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error during scheduled expiration cleanup")
    except asyncio.CancelledError:
        logger.info("Expiration cleanup task cancelled")
