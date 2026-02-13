# Attribution

## Original Concept

Engram is based on the concept of persistent semantic memory for voice assistants, originally implemented by [luuquangvu](https://github.com/luuquangvu) as an SQLite + FTS5 Home Assistant tool.

## Prior Implementation

The core architecture (FastAPI + pgvector + Ollama embeddings, hybrid vector/trigram search) was developed in [ha-semantic-memory](https://github.com/ixanadu/ha-semantic-memory), which served as the direct predecessor to this project.

## What Changed

Engram generalizes ha-semantic-memory from a Home Assistant-specific tool into a standalone semantic memory service for any AI agent. The server code is functionally identical; the changes are:

- Rebranded from `HAMEM_` to `ENGRAM_` configuration prefix
- Home Assistant integration moved to `integrations/homeassistant/`
- Documentation rewritten with a generic-first perspective
- Escalation router stub removed (was a 501 placeholder)
- SQLite migration script removed (not relevant to new installations)
