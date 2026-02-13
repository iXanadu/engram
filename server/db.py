import asyncpg
from pgvector.asyncpg import register_vector

from server.config import settings

pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS memories (
    id              BIGSERIAL PRIMARY KEY,
    namespace       TEXT NOT NULL,
    key             TEXT NOT NULL,
    value           TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'user',
    user_id         TEXT NOT NULL DEFAULT 'default',
    tags            TEXT NOT NULL DEFAULT '',
    tags_search     TEXT NOT NULL DEFAULT '',
    embedding       vector(768),
    search_text     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    UNIQUE (namespace, key, scope, user_id)
);

CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw ON memories
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
CREATE INDEX IF NOT EXISTS idx_memories_key ON memories (key);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories (scope);
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories (user_id);
CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories (namespace);
CREATE INDEX IF NOT EXISTS idx_memories_ns_scope_uid ON memories (namespace, scope, user_id);
CREATE INDEX IF NOT EXISTS idx_memories_search_text_trgm ON memories
    USING gin (search_text gin_trgm_ops);
"""

# Migration: add namespace column to tables created before this column existed.
MIGRATE_SQL = """
DO $$
BEGIN
    -- Add namespace column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'memories' AND column_name = 'namespace'
    ) THEN
        ALTER TABLE memories ADD COLUMN namespace TEXT NOT NULL DEFAULT 'legacy';
        ALTER TABLE memories ALTER COLUMN namespace DROP DEFAULT;
    END IF;

    -- Replace old UNIQUE(key, user_id) with UNIQUE(namespace, key, scope, user_id)
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'memories'::regclass
          AND contype = 'u'
          AND conname = 'memories_key_user_id_key'
    ) THEN
        ALTER TABLE memories DROP CONSTRAINT memories_key_user_id_key;
    END IF;

    -- Create new unique constraint if not exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'memories'::regclass
          AND contype = 'u'
          AND conname = 'memories_namespace_key_scope_user_id_key'
    ) THEN
        ALTER TABLE memories ADD CONSTRAINT memories_namespace_key_scope_user_id_key
            UNIQUE (namespace, key, scope, user_id);
    END IF;
END $$;
"""


async def init_pool() -> asyncpg.Pool:
    global pool
    pool = await asyncpg.create_pool(
        dsn=settings.dsn,
        min_size=2,
        max_size=10,
        init=_init_connection,
    )
    async with pool.acquire() as conn:
        # Run migration first to add namespace column to existing tables,
        # then SCHEMA_SQL handles fresh installs (CREATE TABLE IF NOT EXISTS).
        await conn.execute(MIGRATE_SQL)
        await conn.execute(SCHEMA_SQL)
    return pool


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def close_pool() -> None:
    global pool
    if pool:
        await pool.close()
        pool = None


async def get_pool() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError("Database pool not initialized")
    return pool
