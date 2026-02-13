# Integrations

Engram is a standalone HTTP API. Any system that can make HTTP POST requests can use it as a memory backend.

## Available Integrations

- **[Home Assistant](homeassistant/)** — Pyscript client + Blueprint for HA voice assistants

## Building a Custom Integration

Engram exposes four endpoints, all accepting JSON POST requests:

| Endpoint | Purpose | Required Fields |
|----------|---------|-----------------|
| `POST /memory/set` | Store a memory | `key`, `value` |
| `POST /memory/get` | Retrieve by key | `key` |
| `POST /memory/search` | Semantic search | `query` |
| `POST /memory/forget` | Delete by key | `key` |

### Minimal Example (Python)

```python
import httpx

ENGRAM_URL = "http://localhost:8920"

async def store_memory(key: str, value: str, tags: str = ""):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{ENGRAM_URL}/memory/set", json={
            "key": key,
            "value": value,
            "tags": tags,
            "user_id": "my-agent",
        })
        return resp.json()

async def search_memories(query: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{ENGRAM_URL}/memory/search", json={
            "query": query,
            "user_id": "my-agent",
        })
        return resp.json()["results"]
```

### Scoping

Use `user_id` to isolate memories between different agents or users. Each agent should use a unique `user_id`. The `scope` field provides an additional grouping dimension (defaults to `"user"`).

### Authentication

If the server has `ENGRAM_API_TOKEN` set, include the token in all requests:

```
Authorization: Bearer <token>
```

The `/health` endpoint is always accessible without authentication.
