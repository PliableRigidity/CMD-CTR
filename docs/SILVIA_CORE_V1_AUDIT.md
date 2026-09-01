# SILVIA Core V1 — Phase 0 Audit

## Findings

- Core intent classification was split between the command router, planner regexes, LLM planner, conversation fast paths, workflows, and MAGI.
- Tasks used a minimal `pending`/`done` schema and lacked update, reopen, reschedule, notes, due dates, estimates, cancellation, and verification.
- Task lookup silently selected the first partial match.
- Reminders used a `completed` flag and had no explicit delivered, acknowledged, snoozed, cancelled, or failed lifecycle.
- One-time reminders were marked completed immediately after an attempted Watch Officer notification, with no delivery ledger.
- Reminder pause state was in-memory and reminder mutations did not verify persistence.
- Internal SQLite calendar and Google Calendar were separate user-visible paths. The internal calendar remained the legacy personal API default while newer productivity routes used Google.
- Google Calendar provided list/create/delete but no canonical verified update path.
- Project data was spread across projects, static missions, workspace state, memory, tasks, and hardware projects.
- MAGI could bypass normal conversation grounding when explicit decision mode was selected.
- Cold startup waited on voice and wake-word initialization before exposing the API.
- HTTP client logs could include tokens embedded in URLs.

## Implementation decision

- Reuse and extend the existing task and reminder services rather than creating parallel persistence.
- Apply additive SQLite migrations and retain compatibility aliases.
- Add a small deterministic core conversation layer before social, planner, workflow, and MAGI paths.
- Use Google Calendar as the conversational authority; retain local calendar storage for compatibility rather than deleting data.
- Require mutation verification through a re-read or external retrieval.
- Return explicit error types for validation, ambiguity, absence, authentication, integration, database, and verification failures.
- Move optional startup work to background/lazy initialization.
- Apply redaction at every configured log handler.

## Preserved systems

All memory, project, hardware, workflow, voice, Telegram, infrastructure, and intelligence systems remain present. No vault, database, inventory, conversation, or workflow data was deleted.
