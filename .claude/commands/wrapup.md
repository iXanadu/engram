Document this session's work and prepare for next time:

1. **Store session summary in memory** (`scope=project`):
   - Key: `session/YYYY-MM-DD-brief-desc`
   - Include: what was accomplished, files changed, decisions made, what's next
   - This is the PRIMARY record — no session_progress/ files

2. **Promote lessons to shared memory** (`scope=shared`):
   - Any fix, pattern, or lesson that would help OTHER projects
   - Key prefix: `lesson/` or `fix/`
   - Skip if already stored during the session

3. **Commit changes**:
   - `git add` relevant files (not .env or secrets)
   - `git commit` with descriptive message
   - `git push`

4. **Brief recap**: One paragraph summary of what the next session should know
