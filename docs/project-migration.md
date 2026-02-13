# Project Migration: Files → Memory-First

Migrate a project from legacy `claude/` state files to engram-backed persistent memory.

## When to Use

Run this when entering a project that has a `claude/` directory with state files like:
- `claude/CODEBASE_STATE.md`
- `claude/CONTEXT_MEMORY.md`
- `claude/DEPLOYMENT_STANDARDS.md`
- `claude/session_progress/*.md`
- `claude/SYSTEM_STATE.md`, `claude/ENVIRONMENT_GUIDE.md`, etc.

## Prerequisites

- engram MCP server is running (`memory_status` returns healthy)
- You are in the project's root directory

## Step 1: Verify engram is live

Call `memory_status`. Confirm it returns "Memory service: ok". If not, stop — the service must be running before migrating.

## Step 2: Read all state files

Read every file in the `claude/` directory (not `.claude/`). The key files:

| File | Contains |
|------|----------|
| `CODEBASE_STATE.md` | Architecture, key files, tech stack, conventions |
| `CONTEXT_MEMORY.md` | Cross-session decisions, lessons learned, gotchas |
| `DEPLOYMENT_STANDARDS.md` | Deploy procedures, environments, standards |
| `session_progress/*.md` | Per-session work logs, decisions, blockers |
| `specs/*.md` | PRDs, specifications, design docs |

## Step 3: Triage and store to memory

For each file, extract the **still-relevant** content and store it. Skip anything stale or obsolete.

### CODEBASE_STATE.md → `scope=project`
Store as `key=state/codebase`. This is project architecture — tech stack, key directories, conventions. Keep it concise. Skip file listings that will go stale.

### CONTEXT_MEMORY.md → split between project and shared
- Project-specific decisions → `scope=project`, `key=decision/<topic>`
- Lessons that apply broadly → `scope=shared`, `key=lesson/<topic>`

### DEPLOYMENT_STANDARDS.md → `scope=project`
Store as `key=state/deployment`. Deployment procedures, environments, CI/CD.

### session_progress/*.md → selective
- Read the **most recent 3-5 sessions** for current context
- Store a consolidated summary as `key=session/YYYY-MM-DD-migration-summary` at `scope=project`
- Any lessons or hard-won fixes → `scope=shared` with `key=lesson/<topic>` or `key=fix/<topic>`
- Older sessions: skim for anything still relevant, skip the rest

### specs/*.md → DO NOT migrate to memory
Specs are large reference documents. Leave them in `claude/specs/` — they belong in the repo. Memory is for concise state, not full documents.

## Step 4: Update .claude/ configuration

### .claude/CLAUDE.md (if it exists)
Update to reference memory instead of state files. Remove any instructions about maintaining `claude/CODEBASE_STATE.md` etc. Add a brief project identity section if not already present.

### .claude/commands/startup.md
Replace with memory-first startup:
```
Search persistent memory for this project's context:
1. memory_search with scope=shared — cross-project lessons and patterns
2. memory_search with scope=project — project state, recent sessions, decisions
3. memory_search with scope=machine — local env specifics
4. Read .claude/CLAUDE.md for project identity and conventions
5. Check git status and recent commits
6. Summarize what you know and ask what we're working on
```

### .claude/commands/wrapup.md
Replace with memory-first wrapup:
```
End-of-session wrap-up:
1. Store session summary at scope=project: key=session/YYYY-MM-DD-brief-desc
2. Promote any generalizable lessons to scope=shared with lesson/ or fix/ key prefix
3. Commit any uncommitted code changes
4. Brief recap of what was done and what's next
```

## Step 5: Delete migrated state files

After confirming memories are stored, delete the migrated files:

```bash
# Remove state files (NOT specs — those stay)
rm -f claude/CODEBASE_STATE.md
rm -f claude/CONTEXT_MEMORY.md
rm -f claude/DEPLOYMENT_STANDARDS.md
rm -f claude/SYSTEM_STATE.md
rm -f claude/ENVIRONMENT_GUIDE.md
rm -f claude/TIMELINE.md
rm -rf claude/session_progress/

# If claude/ is now empty (or only has specs/), consider:
# - Keep claude/specs/ if it has useful documents
# - Remove claude/ entirely if nothing useful remains
# - The .gitkeep files are no longer needed
```

## Step 6: Commit

Commit the cleanup with a message like:
```
Migrate project state to engram memory-first pattern

Moved CODEBASE_STATE, CONTEXT_MEMORY, session_progress content to
persistent memory (engram). Updated .claude/ commands to memory-first.
Specs retained in repo.
```

## What NOT to delete

- `claude/specs/` — large reference docs belong in the repo, not memory
- `.claude/CLAUDE.md` — project identity and conventions (keep and update)
- `.claude/commands/` — startup/wrapup commands (keep and update)
- `.claude/settings.local.json` — Claude Code settings (keep as-is)

## Notes

- **Be selective.** Not everything in old state files is worth preserving. Stale architecture notes, outdated file lists, and resolved session blockers can be dropped.
- **Memory keys should be concise.** Store the gist, not the full document. Reference file paths for large content.
- **Specs stay in git.** Memory is for concise, searchable state — not 2000-line PRDs.
- **This is idempotent.** If you've already migrated some content, `memory_store` with the same key overwrites — no duplicates.
