# Blockers

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
