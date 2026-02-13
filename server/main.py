import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.auth import BearerTokenMiddleware
from server.config import settings
from server.db import close_pool, init_pool
from server.embeddings import close_client, init_client
from server.routers import admin, dashboard, health, memory
from server.services.cleanup_task import expiration_cleanup_loop

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting engram service")
    if settings.api_token:
        logger.info("API token authentication ENABLED")
    else:
        logger.info("API token authentication DISABLED (set ENGRAM_API_TOKEN to enable)")
    await init_pool()
    await init_client()
    logger.info("Database pool and embedding client ready")
    cleanup_task = None
    if settings.cleanup_enabled:
        cleanup_task = asyncio.create_task(expiration_cleanup_loop())
    yield
    logger.info("Shutting down")
    if cleanup_task is not None:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    await close_client()
    await close_pool()


app = FastAPI(
    title="engram",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(BearerTokenMiddleware)

app.include_router(memory.router)
app.include_router(admin.router)
app.include_router(health.router)
app.include_router(dashboard.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )
