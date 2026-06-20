# Mission Control Integration

Phase 11 connects Mission Control, project discovery, trusted locations, and file awareness.

## Resolution Flow

When a user says `open Cyberdeck`, SILVIA follows this flow:

```text
User command
  -> planner regex or LLM planner
  -> open_location tool
  -> Trusted Locations registry
  -> real filesystem path check
  -> Explorer launch or honest missing-path response
```

For file search:

```text
User command
  -> find_files or recent_files tool
  -> Trusted Locations registry
  -> file_index refresh if stale
  -> newest-first results
```

## Grounding Rules

- Project and folder names resolve through the registry, not LLM memory.
- Missing locations are reported as unknown.
- Missing paths are reported as missing on disk.
- Multiple search results are shown rather than guessed.
- Launch actions are limited to folders and registered apps.

## Current Integration Points

- `backend/app/tools/planner.py` routes desktop commands.
- `backend/app/services/conversation_service.py` executes desktop tools from chat.
- `backend/app/api/desktop.py` exposes REST endpoints for the UI.
- `frontend/src/components/infrastructure/FilesPanel.jsx` displays folders, recent files, apps, and search results.

