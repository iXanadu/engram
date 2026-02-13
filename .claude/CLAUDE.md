# engram

Generic semantic memory service for AI agents. FastAPI + pgvector + Ollama embeddings.

## Project Structure

- `server/` — FastAPI app (config, db, embeddings, auth, routers, services)
- `integrations/homeassistant/` — Pyscript client + Blueprint for HA voice assistants
- `integrations/README.md` — How to build a custom integration wrapper
- `scripts/` — install/start/restart/uninstall + ollama-warmup + migrate_ha_memory
- `launchd/` + `systemd/` — Service templates
- `tests/` — 28 tests (API, auth, embeddings, e2e, memory_service)
- `docs/` — System prompts, model selection notes

## Commands

- Run server: `uvicorn server.main:app --host 0.0.0.0 --port 8920`
- Run tests: `pytest tests/ -v`
- Health check: `curl http://localhost:8920/health`

## Conventions

- Config prefix: `ENGRAM_` (env vars and `.env` file)
- Database: `engram` (PostgreSQL + pgvector + pg_trgm)
- Default port: 8920
- Embedding model: nomic-embed-text via Ollama (:11434)
- pyenv virtualenv: `engram-3.12` (`.python-version` in repo)
- All memory CRUD goes through `server/services/memory_service.py`
- Schema auto-created on startup; migration SQL handles upgrades from older schemas

## Data Model

Three independent dimensions scope every memory:

| Dimension | Purpose | Examples |
|-----------|---------|----------|
| **namespace** | Which system (required, no default) | `claude-code`, `ha`, `beast` |
| **scope** | Visibility level | `shared`, `machine`, `project`, `user` |
| **user_id** | Identity within namespace | `global`, hostname, dirname, HA UUID |

UNIQUE constraint: `(namespace, key, scope, user_id)`

## Critical Gotchas

- `namespace` is **required** on all API calls — no default. Omitting it returns 422.
- The `engram` DB and `ha_memory` DB both use port 5432. Don't confuse them.
- ha-semantic-memory production at `/opt/srv/ha-semantic-memory` is SEPARATE — don't touch it.
- Both engram and ha-semantic-memory default to port 8920 — can't run simultaneously without overriding `ENGRAM_PORT`.
- Pyscript `@service` decorators MUST use `supports_response="optional"` for HA 2024.10+.

## Related Projects

- `~/projects/ha-semantic-memory` — The original. Production at `/opt/srv/ha-semantic-memory`. Config prefix `HAMEM_`, DB `ha_memory`.
- `~/projects/claude-memory-mcp` — MCP bridge that CC uses to talk to engram. Config has `memory_namespace = "claude-code"`. Installed in `cc-memory-3.12` pyenv.

## State Management

**This project uses memory-first state tracking.** No `claude/CODEBASE_STATE.md` or `claude/session_progress/` files. All session state, decisions, and progress live in persistent memory at `scope=project`. Search memory on startup, store at milestones and session end.
