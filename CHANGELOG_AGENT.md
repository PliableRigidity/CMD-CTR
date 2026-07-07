# Agent Changelog

## 2026-07-07 — QA repair iteration 1 (grounding / sources / routing / latency)

**Failing tests targeted:** hal-005, hal-006, og-001–006, tu-003, tu-004, lat-001

### What changed and why

**`backend/app/services/conversation_service.py`**
- `_brain63_entity_answer`: Changed return type from `str | None` to `Brain63Answer | None`
  so callers get the source-path list alongside the text.
- Added `_grounded_brain63_response(title, answer)` helper: builds `AssistantResponse`
  with `sources` populated from Brain63 file paths (rule 6 of GROUNDING_POLICY.md).
- Added `_projects_from_brain63_or_registry(query, category)` helper: tries Brain63 search
  first; falls back to static `list_projects()` registry.
- Added `_brain63_sources_for_query(query)` helper: extracts `SourceReference` list for
  entities detected in a query — used to attach evidence to LLM-path responses.
- Updated 4 call sites in `_handle_entity_query` to use `_grounded_brain63_response`
  instead of `_simple_response("Brain63", ...)` so sources are never empty.
- Pre-social interceptor for `_DECISION_QUERY_RE`: catches "what did I decide about X?"
  BEFORE the social engine, ensuring Brain63 is searched and no hallucination occurs.
- Pre-social interceptor for category project queries ("what are my robotics projects?"):
  routes to `_projects_from_brain63_or_registry`.
- Pre-social interceptor for explicit Obsidian/Brain63 queries.
- Updated `_MY_PROJECTS_RE` handler (both early + inside `_handle_local_command`) to use
  `_projects_from_brain63_or_registry` so sources are attached.
- Social LLM path: attach `_brain63_sources_for_query` result to `sources` field when
  Brain63 context was fetched (e.g., hal-006 "Give me a quick update on Silvia").
- Operational LLM path: same source attachment.

**`backend/app/tools/planner.py`**
- Added `_HW_PROJ_NATURAL_Q` pattern: "What hardware projects do I have?" → `list_hw_projects`
- Added `_HW_INVENTORY_NATURAL_Q` pattern: "What's in my hardware inventory?" → `hw_inventory_summary`
- Wired both into `_regex_hardware` (fixes tu-003, tu-004 tool routing).

**`backend/app/services/conversation_state.py`**
- Added "are you online?" / "hello, are you online?" to `_QUICK_SOCIAL` deterministic
  replies for zero-LLM latency (fixes lat-001 9.5 s greeting).

## 2026-07-07 — Autopilot v2: real autonomous repair loop

- Rewrote `agent/run_silvia_autopilot.py`: backend start/verify, git
  checkpoint before every repair, configurable coding-agent invocation
  (prompt piped to stdin), before/after score comparison, keep-if-improved /
  rollback-if-worse, protected-file and Obsidian-vault guards, stop
  conditions, and full reporting (`autopilot_latest.md`, history, JSON logs).
- New CLI: `--report-only` (safe default) and `--auto-repair [--max-iterations N]`.
- `agent/config.example.json` extended: backend/test/agent commands, timeouts,
  `max_iterations`, `max_same_failure_attempts`, `auto_commit`,
  `rollback_on_worse`.
- Harness files and test cases are write-protected against the repair agent;
  changes there roll back and abort the loop.

Every change made by a coding agent to this repository must be logged here:
date, what changed, why, and files touched. See AGENT.md rule 8.

## 2026-07-07 — QA & repair-preparation foundation (v1)

- Created `agent/` autonomous QA system: test runner (`run_tests.py`),
  rule-based evaluator (`evaluate_results.py`), HTTP adapter
  (`silvia_client.py`), failure-report generation, repair-prompt generator
  (`generate_repair_prompt.py`), conservative autopilot
  (`run_silvia_autopilot.py`), config example, and 25 test cases across
  obsidian_grounding / hallucination / latency / voice_pipeline / tool_usage.
- Created root policy & log files: `AGENT.md`, `GROUNDING_POLICY.md`,
  `TEST_LOG.md`, `FAILURE_LOG.md`, `BLOCKERS.md`, this file.
- No existing SILVIA code was modified. Auto-repair intentionally not enabled.
- Verified live against the running backend (port 8001, auto-resolved from
  `.env` APP_PORT): 14/25 pass. Calibrated two harness false positives found
  during verification (vp-001 voice-status shape; hal-003/tu-002 honest-answer
  phrasings). Confirmed genuine hallucination catch: SILVIA fabricated a
  "council decision" for the fake Project Nebula (hal-005).
