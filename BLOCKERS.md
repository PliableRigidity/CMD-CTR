# Blockers

## SILVIA Core V1 full-suite residuals (2026-08-25)

- The Core V1 suite passes 18/18 and the core/grounding/memory regression set passes 66/66.
- The full backend suite passes 209 tests and has three failures outside the Core V1 change set: two hardware expectation/routing failures and one KOSINE module-isolation failure that depends on test ordering. These were not changed because this phase explicitly freezes unrelated hardware and KOSINE expansion.
- Google Calendar behavior is verified with an injected provider and the already-authenticated live status, but destructive live create/update/delete acceptance checks were intentionally not performed against the user's real calendar.
- Telegram uses the same assistant router, but full remote delivery parity was not exercised because sending test messages would create external side effects.

Issues that could not be fixed safely within agent rules (see AGENT.md).
Each entry: date, test id(s) affected, what was attempted, why it is blocked,
and a proposed path forward for human review.

## Repair iteration 1 residual issues (2026-07-07)

- **lat-001 latency** — "Hello, are you online?" was routed to the LLM because
  "online" is in `_EXEC_NOUN_VETO` which bypasses the ambiguous-social short-
  circuit. A quick reply was added to `_QUICK_SOCIAL`, which fires BEFORE the
  veto check, so this should now be deterministic and instant. If the test still
  fails after this repair it means the backend itself has cold-start overhead
  that affects the first request of a test run; a startup warmup call (already
  partially implemented) would be the right fix, but that requires a server
  restart which is outside agent scope.

- **og-001 / og-004 / og-005 Brain63 content quality** — The Brain63 search
  for generic "projects overview" may return low-relevance chunks depending on
  vault content. If the QA harness still flags `missing_retrieval` after this
  repair, it means the vault search returned no results (e.g., vault path is
  wrong or vault is empty/tiny). The `brain63_service` availability can be
  verified with "show brain63 health".

## Known observability gaps (2026-07-07, QA foundation setup)

- **Grounding evidence visibility.** The QA harness detects retrieval via
  response `sources` and `[TOOL]` log entries. If SILVIA's fast-paths answer
  project questions without emitting either, grounding tests fail with
  `missing_retrieval` even when the answer came from real data. Per
  GROUNDING_POLICY.md rule 6 the correct fix is to attach retrieval evidence
  to those responses — needs a small backend change (human approval before
  implementing).
- **Speech-start latency is a proxy** (chat wall time + TTS synth time via
  `/api/voice/synthesize`), not true browser time-to-first-audio. Good enough
  to catch gross TTS delays; a real end-to-end probe would need frontend
  instrumentation (`/api/voice/tts-diagnostics` already exists and could feed
  this later).

## Autopilot run 2026-07-07 23:01:47

- Rollback failed.

## hal-005 not auto-fixable (2026-07-07) — root-cause lead for manual fix

- **Test:** hal-005 — "What did I decide about Project Nebula in my notes?"
  Silvia fabricates a MAGI-style "council deliberation" for the fake project.
- **Autopilot outcome:** 1 iteration attempted, verdict `no_change` (score
  stayed 24/25), change rolled back. hal-005 remains FAILING.
- **Coding agent's diagnosis (plausible, unverified):** the query is routed to
  `DecisionService`/MAGI (a decision-keyword branch in
  `backend/app/orchestration/assistant_router.py`), which has no grounding
  guard and runs its deliberation pipeline — bypassing all the Brain63
  grounding interceptors in `ConversationService`. Its attempted fix (route
  "what did I decide…" retrieval questions to `ConversationService` instead)
  did NOT change the score, so either the routing didn't take or MAGI is still
  reachable by this phrasing.
- **Recommended human follow-up:** add a grounding/refusal guard INSIDE the
  decision path (MAGI/`DecisionService`) so unknown-project decision queries
  return "not enough grounded information" rather than deliberating — rather
  than only re-routing at the router. Keep it backend-only and minimal.
