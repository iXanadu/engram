#!/usr/bin/env python3
"""Migrate memories from ha_memory database to engram database.

Maps user_id patterns to the new (namespace, scope, user_id) triple:
  - "cc-shared"       → namespace=claude-code, scope=shared,  user_id=global
  - "cc-proj-<name>"  → namespace=claude-code, scope=project, user_id=<name>
  - "cc-<hostname>"   → namespace=claude-code, scope=machine,  user_id=<hostname>
  - everything else   → namespace=ha,          keep existing scope/user_id

Idempotent: uses ON CONFLICT DO NOTHING. Safe to re-run.
Copies embeddings directly — no re-embedding required.
"""

import argparse
import asyncio
import os
import sys

import asyncpg


def classify_row(row: dict) -> dict:
    """Map a ha_memory row to engram's (namespace, scope, user_id) triple."""
    uid = row["user_id"]
    scope = row["scope"]

    if uid == "cc-shared":
        return {"namespace": "claude-code", "scope": "shared", "user_id": "global"}
    elif uid.startswith("cc-proj-"):
        return {"namespace": "claude-code", "scope": "project", "user_id": uid[len("cc-proj-"):]}
    elif uid.startswith("cc-"):
        return {"namespace": "claude-code", "scope": "machine", "user_id": uid[len("cc-"):]}
    else:
        return {"namespace": "ha", "scope": scope, "user_id": uid}


async def migrate(source_dsn: str, target_dsn: str, dry_run: bool = False) -> None:
    src_pool = await asyncpg.create_pool(dsn=source_dsn, min_size=1, max_size=2)
    tgt_pool = await asyncpg.create_pool(dsn=target_dsn, min_size=1, max_size=2)

    try:
        async with src_pool.acquire() as src_conn:
            rows = await src_conn.fetch(
                """SELECT key, value, scope, user_id, tags, tags_search,
                          embedding, search_text, created_at, last_used_at, expires_at
                   FROM memories"""
            )

        print(f"Source rows: {len(rows)}")

        if dry_run:
            for row in rows:
                mapped = classify_row(dict(row))
                print(f"  {row['user_id']:30s} → ns={mapped['namespace']:12s} scope={mapped['scope']:8s} uid={mapped['user_id']}")
            print(f"\nDry run complete. {len(rows)} rows would be migrated.")
            return

        migrated = 0
        skipped = 0

        async with tgt_pool.acquire() as tgt_conn:
            for row in rows:
                mapped = classify_row(dict(row))
                result = await tgt_conn.execute(
                    """INSERT INTO memories
                       (namespace, key, value, scope, user_id, tags, tags_search,
                        embedding, search_text, created_at, last_used_at, expires_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                       ON CONFLICT (namespace, key, scope, user_id) DO NOTHING""",
                    mapped["namespace"],
                    row["key"],
                    row["value"],
                    mapped["scope"],
                    mapped["user_id"],
                    row["tags"],
                    row["tags_search"],
                    row["embedding"],
                    row["search_text"],
                    row["created_at"],
                    row["last_used_at"],
                    row["expires_at"],
                )
                if result == "INSERT 0 1":
                    migrated += 1
                else:
                    skipped += 1

        print(f"Migration complete: {migrated} migrated, {skipped} skipped (already exist), {len(rows)} total")

    finally:
        await src_pool.close()
        await tgt_pool.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate ha_memory → engram with namespace mapping")
    parser.add_argument(
        "--source-dsn",
        default=os.environ.get("SOURCE_DSN", "postgresql://engram:engram@localhost:5432/ha_memory"),
        help="Source database DSN (default: $SOURCE_DSN or postgresql://engram:engram@localhost:5432/ha_memory)",
    )
    parser.add_argument(
        "--target-dsn",
        default=os.environ.get("TARGET_DSN", "postgresql://engram:engram@localhost:5432/engram"),
        help="Target database DSN (default: $TARGET_DSN or postgresql://engram:engram@localhost:5432/engram)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without writing",
    )
    args = parser.parse_args()

    print(f"Source: {args.source_dsn}")
    print(f"Target: {args.target_dsn}")
    if args.dry_run:
        print("Mode: DRY RUN")
    print()

    asyncio.run(migrate(args.source_dsn, args.target_dsn, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
