# SILVIA Scheduling + V2 Status

Date: 25 August 2026

This is a conservative implementation report. `RELIABLE` means the behavior has broad automated coverage and restart/error testing; `PARTIAL` means a working path exists but important scenarios remain.

## Executive summary

SILVIA now has a shared, timezone-aware natural date interpreter and a canonical `/api/scheduling` surface used by the separate Practical UI. The original command-center frontend remains unchanged by this task and continues on port 5173. SILVIA V2 runs independently on port 5174 against the same backend and persistent SQLite records.

The exact regression request—`add a new event for 27th August. Ishaan Birthday`—now extracts the correct title, resolves 27 August 2026, applies the birthday all-day policy, persists the event, reads it back, and returns the verified record.

## Before

- Date parsing lived in `personal_tool.py` and used naive machine-local datetimes.
- Event extraction expected the title before a narrow set of date expressions.
- Ordinals and filler such as `for 27th August` were not handled together.
- Local calendar records lacked timezone, all-day, external ID, and updated timestamps.
- Frontends had no single combined feed for event/task/reminder dates.
- Google Calendar and local calendar paths remain historically separate.

## After

- `datetime_service.py` is the shared structured interpretation layer.
- Results include resolved date/time, local and UTC ISO values, timezone, precision, all-day/needs-time flags, recurrence, ambiguity, and original input.
- Parsing tolerates filler and common absolute, relative, weekday, day-part, clock, and recurring expressions.
- A canonical scheduling API supports parse, natural event creation, verified local event CRUD, and a combined month overview.
- Calendar schema uses additive migrations only and retains existing data.
- The V2 month grid derives one marked-date set from real events, tasks, and reminders; related or repeated items cannot render multiple dots in a cell.

## Reliability matrix

| Area | Status | Evidence / limitation |
|---|---|---|
| Date parsing | **RELIABLE** | Deterministic unit coverage for requested date variants, relative phrases, weekdays, ordinals, filler, BST conversion, and regression phrasings. |
| Local events | **PARTIAL** | Natural all-day creation, structured create/update/delete/query, read-back verification, additive schema, and deduplicated month feed work. Ambiguous title matching and every chat reschedule/delete phrasing are not comprehensively implemented. |
| Reminders | **PARTIAL** | Persistent lifecycle fields, verified CRUD, snooze, acknowledgement, cancellation, recurrence metadata, and scheduler ledger exist from Core V1. Full crash-window exactly-once delivery cannot be guaranteed. |
| Recurrence | **PARTIAL** | Daily, weekly, monthly, weekday parsing and persisted recurrence exist. Calendar-grade recurrence rules and exhaustive restart/failure testing remain. |
| Google integration | **PARTIAL** | Existing Google adapter is retained and has typed create/get/update/delete behavior. The new V2 overview currently uses dependable local calendar records; complete aggregation and deduplication across Google and local sources remains. |
| Persistence | **PARTIAL** | SQLite records and additive migrations survive process restart. Core persistence tests pass; a long-running real-time delivery soak test was not performed. |
| Grounding | **PARTIAL** | Scheduling API returns typed errors and never fabricates state. Some legacy conversational paths still bypass the canonical service. |
| V2 UI integration | **PARTIAL** | Real chat, tasks, projects, combined scheduling overview, natural events, and quick actions are wired. Reminder quick-create uses the real chat path. Advanced pages link to legacy UI rather than duplicating it. |
| Legacy UI | **RELIABLE** | Kept as a separate package and remains available on its original port. No visual redesign was made as part of V2. |

## Missing-time policy

- Birthday, anniversary, holiday, and explicit `all day` events become all-day events.
- Appointment-like events without a time return a `needs_time` clarification; SILVIA does not invent a time.
- Date-only tasks retain the compatibility default used by Core V1.
- Reminder creation through canonical conversational behavior requires meaningful scheduling; the legacy compatibility wrapper still supplies its historical default where older callers require an absolute timestamp.

## Root cause of the original failure

The legacy extractor removed the command prefix and then tried a title-first regular expression with only `tomorrow`, weekdays, or numeric slash dates. The remaining text began with `for 27th August`, used an ordinal, and placed the title after a period. It fell through with an empty start string, producing the parse error. The new extractor accepts either title/date order and sends the unsanitized date phrase to the shared parser.

## Database migration

`calendar_events` receives additive columns only: `timezone`, `all_day`, `external_calendar_id`, and `updated_at`. Existing rows and IDs are preserved. Reminder and task lifecycle migrations from Core V1 are also additive.

## Tests

- Scheduling V2 + Core V1 focused suite: **32 passed**.
- V2 production build: **passed** (Vinext/Vite, all five build phases).
- Live backend health: HTTP 200.
- Live V2 page: HTTP 200.
- Live regression create/read-back/delete: passed.
- Earlier Core V1 verification: 66 relevant tests passed; full backend run had 209 passes and 3 unrelated pre-existing failures (two hardware cases and one KOSINE ordering isolation case).

## Launch and coexistence

Backend:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

Legacy UI:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

V2 Practical UI:

```powershell
cd silvia_v2_ui
npm run dev -- --host 127.0.0.1 --port 5174
```

- Legacy: <http://127.0.0.1:5173/>
- V2: <http://localhost:5174/>
- Backend: <http://127.0.0.1:8001/>

Both UI packages run independently and call the same backend. V2 does not replace or import the legacy frontend.

## V2 views

- **Today:** greeting, compact month, selected-day agenda, focus suggestion, and quick create.
- **Chat:** full-width readable conversation with clear operator/SILVIA distinction and busy/error feedback.
- **Tasks:** simple real-data list.
- **Calendar:** larger month plus selected-day agenda.
- **Projects:** useful real-data project list.
- **Advanced:** Hardware, Systems, Memory, and Dev remain intentionally secondary and link to command-center capabilities.
- Responsive navigation collapses to a five-item bottom bar on narrow screens.

## Known limitations

1. The active persisted timezone preference on the currently running installation is `Asia/Tokyo`; it overrides the configured default. The London parser regression uses an explicit `Europe/London` test context and passes. Change the user preference through SILVIA if London should be active at runtime.
2. Google Calendar is not yet the sole canonical storage adapter for V2, so cross-source aggregation remains partial.
3. Conversational references such as “actually make that 6” are covered for Core V1 task behavior but are not exhaustively reliable across every reminder/event conversation and session boundary.
4. Exactly-once reminder delivery across an operating-system crash at the delivery boundary is not provable without an external transactional queue.
5. No existing user data was wiped or destructively migrated.
