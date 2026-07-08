# KOSINE Integration (Phase 19)

SILVIA's transition from Brain63 (Obsidian/Markdown) to **KOSINE** (local-first
structured memory) as its primary knowledge backend. Migration is **gradual,
reversible, and additive** — Brain63 is never removed, only demoted to a
read-only fallback/backup.

## Architecture

```
SILVIA
  └─ MemoryManager  (backend/app/services/memory_manager.py)
       priority (when KOSINE_PRIMARY): [kosine, project_memory, knowledge_graph,
                                        workflow_history, session_memory, sqlite, brain63]
        ├─ KosineProvider ──┐
        │                   └─ kosine_client (singleton) ─→ kos.sdk.KOSClient ─→ kosine.db
        └─ Brain63Provider  ─→ Obsidian vault  (READ-ONLY fallback / human archive)

  KosineMigrationService  ─→ kos.importing (preview/run) + kos.backups  (Brain63 vault → KOSINE)
  KosineMaintenanceService ─→ read-only scan → WorkflowEngine drafts (suggestions only)
  KosineAuditLog          ─→ data/kosine_audit.jsonl  (every SILVIA write)
```

Transport is **in-process** by default (`KOSClient(db_path=...)`). Set
`KOSINE_BASE_URL` to talk to a running KOSINE REST server instead.

## Files

| Concern | File |
|---|---|
| Config flags | `backend/config.py` (`KOSINE_*`) |
| Client singleton | `backend/app/memory/kosine_client.py` |
| Memory provider | `backend/app/memory/kosine_provider.py` |
| Write audit log | `backend/app/memory/kosine_audit.py` |
| Migration service | `backend/app/services/kosine_migration.py` |
| Maintenance loop | `backend/app/services/kosine_maintenance.py` |
| Suggestion apply handler | `backend/app/services/kosine_apply.py` |
| API router | `backend/app/api/kosine.py` (`/api/kosine/*`) |
| Frontend board | `frontend/src/pages/KosinePage.jsx` (`/kosine`) |
| Chat navigation | planner board router (`open kosine board`, `go to kosine`) |

## Config flags (all default OFF)

| Flag | Effect |
|---|---|
| `KOSINE_ENABLED` | Register the KOSINE provider. |
| `KOSINE_PRIMARY` | Promote KOSINE to first read priority; Brain63 → fallback. |
| `KOSINE_DB_PATH` | Target SQLite db (default `<KOSINE_REPO_PATH>/kosine.db`). |
| `KOSINE_BASE_URL` | Use REST mode instead of in-process SDK. |
| `KOSINE_REPO_PATH` | sys.path fallback if `kos` isn't pip-installed. |
| `KOSINE_ALLOW_WRITES` | Permit SILVIA-originated create/update (audited). |
| `KOSINE_MAINTENANCE_AUTODRAFT` | Let the maintenance loop draft suggestion workflows. |

## Rollout (each step reversible via its flag)

1. `KOSINE_ENABLED=true` — KOSINE appears as a provider (appended, not primary). Verify `/api/kosine/status`.
2. `POST /api/kosine/migrate/preview` → `POST /api/kosine/migrate` — import Brain63 (backup taken first).
3. `KOSINE_PRIMARY=true` — KOSINE becomes the first read source; Brain63 stays as fallback.
4. `KOSINE_ALLOW_WRITES=true` — enable audited writes.
5. `KOSINE_MAINTENANCE_AUTODRAFT=true` — maintenance drafts suggestion workflows.

## Safety guarantees

- **Non-destructive transport.** The shared client is created with
  `allow_destructive=False`, so KOSINE's delete/merge tools can never fire from SILVIA.
- **Gated writes.** Create/update require `KOSINE_ALLOW_WRITES`; every write is
  recorded to `data/kosine_audit.jsonl` with the touched `objects_changed` /
  `events_created` ids (auditable + reversible).
- **Reversible migration.** `migrate()` snapshots the KOSINE db (KOSINE
  `BackupManager`) before importing; `restore()` rolls back. The importer is
  idempotent, so re-running is a no-op for unchanged notes.
- **Suggestions, not actions.** The maintenance loop only ever produces
  WorkflowEngine *drafts* (never auto-submitted, never executed), and only when
  autodraft is enabled. `scan()` is strictly read-only.
- **Brain63 preserved.** Never modified or deleted — remains the read-only,
  human-readable archive and fallback.

## Approval-gated suggestion execution (Phase 19b)

The maintenance loop only ever produces WorkflowEngine **drafts**
(`category=kosine_suggestion`). Turning an approved suggestion into a KOSINE
write is the job of the dedicated **apply handler** — the WorkflowEngine owns
approval state but never mutates KOSINE itself.

```
suggestion → workflow draft → user approves → kosine_apply validates:
    · category == kosine_suggestion
    · KOSINE_ENABLED
    · tool ∈ {create_memory, update_memory, create_relationship, add_event}  (non-destructive)
    · workflow is approved
    · KOSINE_ALLOW_WRITES        (real execution only; dry-run is exempt)
  → kosine_audit.audited_write(...) → audit record → workflow completed | failed
```

Guarantees: no execution when `KOSINE_ALLOW_WRITES=false`; no destructive ops
(allowlist here + destructive tools disabled at transport); every applied
suggestion produces an audit record; a failed write marks the workflow `failed`,
never `completed`; a dry-run writes nothing and leaves status unchanged.

**Chat commands**
- `apply kosine suggestion WF-042` — apply an already-approved suggestion
- `approve and apply kosine suggestion 42` — approve then apply (accepts bare numbers)
- append `dry run` to preview without writing

**Dashboard controls** (`/kosine` → Suggestions panel) — status-gated buttons
Submit for review · Approve · Reject · Dry run apply · Approve & apply. They call
the state endpoints (`/submit`, `/approve`, `/reject` — WorkflowEngine only) and
the single execution endpoint (`/apply`). "Approve & apply" is disabled with an
explanation when `KOSINE_ALLOW_WRITES=false`; dry-run stays available and shows
the exact operation; the audit log below reflects successful applies.

## API

`GET /api/kosine/status` · `POST /api/kosine/migrate/preview` ·
`POST /api/kosine/migrate` · `GET /api/kosine/backups` · `POST /api/kosine/restore` ·
`GET /api/kosine/audit` · `GET /api/kosine/maintenance/scan` ·
`POST /api/kosine/maintenance/run` · `GET /api/kosine/suggestions` ·
`POST /api/kosine/suggestions/{code}/apply`  (body: `{approve, dry_run}`)
