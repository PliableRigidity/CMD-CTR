# File Awareness

File awareness is backed by a local SQLite index in `data/cmdctr.db`.

## Data Model

The `file_index` table stores:

- `path`
- `name`
- `extension`
- `location_id`
- `location_name`
- `size_bytes`
- `modified_ts`
- `indexed_at`

## Indexing

SILVIA scans trusted locations and skips heavy/generated folders such as:

- `.git`
- `node_modules`
- `__pycache__`
- `.venv`
- `dist`
- `build`

Indexes refresh automatically when search or recent-file commands run and the cached location is stale. The current refresh TTL is five minutes.

## Search Behavior

Supported filters:

- Filename or path query
- Extension
- Trusted location
- Recent files by modified time

Extension aliases:

- `pcb` maps to `kicad_pcb`
- `schematic` and `sch` map to `kicad_sch`

Search results are newest-first. If nothing exists, SILVIA reports that no files were found instead of inventing paths.

