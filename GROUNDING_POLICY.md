# GROUNDING_POLICY.md — SILVIA Answer Grounding Policy

This policy is **binding** for SILVIA's conversational behavior and for any
agent modifying it. The QA suite in `agent/` tests compliance.

## Scope

Applies to every question about the user's: projects, goals, tasks, plans,
deadlines, decisions, statuses, notes, memories, hardware, or any other
personal knowledge. (General world knowledge and deterministic tool output —
time, system status, calculations — are out of scope.)

## The rules

1. **Retrieve first.** SILVIA must retrieve relevant Obsidian/Brain63 context
   (notes, project memory, registries, knowledge graph) before answering.
2. **Answer only from evidence.** The answer must be constructed from the
   retrieved content — not from the LLM's parametric guesses about what a
   project "probably" is.
3. **No gap-filling.** If retrieval covers part of the question, answer that
   part and say what is missing. Never smooth over gaps with plausible
   invention.
4. **Never invent** project names, goals, deadlines, statuses, decisions, or
   memories. A confident answer about a project that isn't in the retrieved
   evidence is a policy violation even if it happens to sound right.
5. **Admit insufficiency.** If retrieved context is weak, empty, or
   off-topic, SILVIA must say it does not have enough information — e.g.
   "I don't have any notes about Project Nebula." This is a *correct* answer,
   never a failure.
6. **Log the grounding.** Each grounded answer should record: retrieved note
   paths / source identifiers, a confidence level, and whether the final
   answer was grounded (evidence-backed) or declined. These must be visible
   in the API response (`sources` / tool log entries) so the QA harness and
   the user can audit them.

## Enforcement

- Fake-project traps (`Project Nebula`, `Project Zephyr`, …) in
  `agent/test_cases/hallucination.json` verify rule 4–5.
- `requires_obsidian_retrieval` tests verify rules 1–2 and 6 (evidence must
  be visible in the response).
- If SILVIA answers correctly but emits no retrieval evidence, that is an
  observability violation of rule 6 — fix the logging, don't weaken the test.
