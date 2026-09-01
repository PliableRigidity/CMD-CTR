# KOSINE Integration — Setup & Operations

Everything defaults OFF; nothing changes until you opt in.

## Prerequisites

- SILVIA (this repo) runnable: `python main.py` (backend on `APP_PORT`, `.env`
  sets it to **8001**) and `cd frontend && npm run dev` (Vite).
- KOSINE checked out at `C:\Users\IshaanV\Documents\GitHub\KOS` (or set
  `KOSINE_REPO_PATH`). No changes to KOSINE are needed or made.
- KOSINE runs as its **own independent service** — SILVIA talks to it over HTTP.

## Configuration (SILVIA `.env`)

```ini
# Memory router mode: ""(auto) | brain63 | kosine | hybrid
MEMORY_MODE=hybrid

# KOSINE — compliant REST transport (no import kos, no DB access)
KOSINE_ENABLED=true
KOSINE_TRANSPORT=rest
KOSINE_BASE_URL=http://127.0.0.1:8000
KOSINE_TIMEOUT_SECONDS=15
KOSINE_MAX_RETRIES=2
KOSINE_API_TOKEN=                 # only if you enabled KOSINE auth
KOSINE_PRIMARY=false              # true → KOSINE first, Brain63 fallback
KOSINE_ALLOW_WRITES=false         # keep off until reads are validated
KOSINE_MAINTENANCE_AUTODRAFT=false

# Migration runs via KOSINE's own CLI (spec-compliant)
KOSINE_CLI=                       # "" = auto (kosine on PATH, else python kos.py)
KOSINE_REPO_PATH=C:/Users/IshaanV/Documents/GitHub/KOS
KOSINE_DB_PATH=                   # "" = <repo>/kosine.db
```

## Starting KOSINE (independently)

```bash
cd C:/Users/IshaanV/Documents/GitHub/KOS
python server.py                  # REST API on 127.0.0.1:8000
# health check:
curl http://127.0.0.1:8000/health
```

## Starting SILVIA

```bash
python main.py                    # backend :8001
cd frontend && npm run dev        # UI
```

Open the **Cognitive** board (TopBar → Cognitive, or `/cognitive`). Type a task
in "run a cognition query…" and press Run to see live memory retrieval,
activation, reranking, expansion, and context selection.

## Provider modes (rollout order)

1. **Read-only, hybrid** — `KOSINE_ENABLED=true`, `MEMORY_MODE=hybrid`, writes
   off. Validate retrieval + the graph.
2. **KOSINE primary** — `KOSINE_PRIMARY=true` (or `MEMORY_MODE=kosine`); Brain63
   becomes fallback.
3. **Writes** — `KOSINE_ALLOW_WRITES=true`; proposals still require approval in
   the `/kosine` board.
4. **Maintenance autodraft** — `KOSINE_MAINTENANCE_AUTODRAFT=true` (suggestions
   only; nothing auto-applies).

## Migration (optional, via KOSINE CLI)

Run when the KOSINE service is idle (KOSINE owns its DB):

```bash
# preview (writes nothing)
curl -X POST http://localhost:8001/api/kosine/migrate/preview
# apply (backs up KOSINE first, then imports the Brain63 vault)
curl -X POST http://localhost:8001/api/kosine/migrate -d '{"backup":true}'
```

Rollback: `POST /api/kosine/restore {"backup_name":"…","confirm":true}`. Brain63
is never modified. See `docs/brain63_migration_strategy.md`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/api/kosine/status` shows unavailable | KOSINE service not running, or wrong `KOSINE_BASE_URL`. Start `python server.py`; check `/health`. |
| Cognitive graph empty | No activity yet — run a query, or `KOSINE_ENABLED=false` so only Brain63 answers. |
| Provider-degradation banner | KOSINE unreachable; SILVIA is correctly degrading to Brain63. |
| 401 on cognitive endpoints | `API_KEY` is set and you're not localhost — supply `X-API-Key` / WS `?api_key=`. |
| Migration says "requires KOSINE_TRANSPORT=local" | Not applicable to CLI migration; ensure `KOSINE_CLI`/`KOSINE_REPO_PATH` resolve the `kosine` CLI. |
| Writes never apply | `KOSINE_ALLOW_WRITES=false` (by design) or the suggestion isn't approved in `/kosine`. |
