# SILVIA Autonomous QA & Repair-Preparation System

Automated testing, failure reporting, and repair-prompt generation for
SILVIA. This is the foundation for a future closed auto-repair loop —
today it tests, evaluates, logs, and prepares prompts; it does **not**
call a coding agent or modify code by itself.

## What it does

1. **`run_tests.py`** — sends test questions to the live SILVIA backend
   (`POST /api/chat`) and probes voice endpoints (`/api/voice/*`), capturing
   answers, retrieval sources, tool calls, and wall-clock latency.
2. **`evaluate_results.py`** — transparent rule-based checks: required/forbidden
   terms, retrieval evidence, hallucination traps (fake projects), latency
   thresholds, tool-call expectations. No LLM judge.
3. **Failure report** — `reports/latest_failure_report.md` (archived per run in
   `reports/history/`).
4. **`generate_repair_prompt.py`** — turns the failure report into a focused,
   rule-bound prompt for Claude/Codex (`reports/latest_repair_prompt.md`).
5. **`run_silvia_autopilot.py`** — the autonomous loop. `--report-only` runs
   steps 1–4; `--auto-repair` runs the full test → repair → retest cycle with
   git checkpoints, keep/rollback decisions, and safety guards (see below).

## How to run

The backend must be running first (from the repo root):

```bash
python main.py            # starts SILVIA on http://localhost:8000
```

Then, in another terminal (repo root, same Python env as the backend is fine,
but the harness itself is stdlib-only — any Python 3.10+ works):

```bash
python agent/run_tests.py                     # full suite
python agent/run_tests.py --category latency  # one category
python agent/run_tests.py --id hal-001        # one test
python agent/run_silvia_autopilot.py          # tests + report + repair prompt
python agent/generate_repair_prompt.py        # regenerate prompt from last report
```

If the backend is **not** running, the suite still completes — every test is
recorded as an honest `silvia_unreachable` failure. Results are never faked.

Optional config: copy `config.example.json` → `config.json` to change
`base_url` or timeouts.

## How to read the outputs

| File | What it is |
|---|---|
| `agent/logs/run_<ts>.json` | Full machine-readable results for one run |
| `agent/reports/latest_failure_report.md` | Human-readable failure report (counts, categories, per-failure detail + fix direction) |
| `agent/reports/history/` | Archived report per run |
| `agent/reports/latest_repair_prompt.md` | Ready-to-paste prompt for a coding agent |
| `TEST_LOG.md` (repo root) | Appended per-run summary (every test, PASS/FAIL, latency) |
| `FAILURE_LOG.md` (repo root) | Appended failures only |

## How to add test cases

Add an object to any file in `agent/test_cases/*.json` (or create a new
`.json` file — the category defaults to the file stem). Supported fields are
documented at the top of [evaluate_results.py](evaluate_results.py). Minimal example:

```json
{
  "id": "og-007",
  "category": "obsidian_grounding",
  "question": "What did I write about the drone project?",
  "requires_obsidian_retrieval": true,
  "must_not_invent": true,
  "expected_behavior": "Answer only from retrieved notes.",
  "failure_type": "grounding"
}
```

Conventions: unique `id`, keep hallucination traps pointing at projects that
do **not** exist (Nebula, Zephyr), and never put private/secret data in test
cases — they are committed to git.

## Current limitations (honest list)

- **Grounding detection is heuristic.** Retrieval evidence = response
  `sources` + `[TOOL]` log entries matching knowledge-related names. If SILVIA
  answers correctly via a path that emits neither, the test fails with
  `missing_retrieval` — that is a real observability gap worth fixing in the
  backend (per GROUNDING_POLICY.md, retrieval should be logged), not a reason
  to weaken the check.
- **Hallucination detection is marker-based.** "Did it admit uncertainty?" is
  a substring check over a phrase list, plus forbidden-pattern regexes (e.g.
  dates for fake-project deadlines). No semantic judge yet.
- **Speech-start latency is a proxy**: chat wall-time + TTS synth time of the
  answer's first 200 chars. It does not measure browser audio playback.
- **Tool-call capture depends on response logs** (`[TOOL] …` entries). Tools
  that don't emit there are invisible to the harness.
- Latency thresholds are single-shot wall-clock — a cold model load can fail a
  run that would pass warm. Rerun before treating one latency failure as real.
- No LLM judge, no CI integration, no auto-repair yet.

## Autonomous repair (autopilot)

```bash
python agent/run_silvia_autopilot.py --report-only                 # safe: tests + reports only
python agent/run_silvia_autopilot.py --auto-repair                 # full loop (config max_iterations)
python agent/run_silvia_autopilot.py --auto-repair --max-iterations 2
```

Per iteration the autopilot:
1. Starts the backend if it isn't running (and stops it again at the end).
2. Creates a **git checkpoint commit** (includes any pre-existing uncommitted
   work so rollback is lossless; runtime `logs/` are excluded from commits).
3. Generates the repair prompt and pipes it to the configured coding agent
   (`coding_agent_command` + `coding_agent_args`, prompt on stdin — agent-CLI
   agnostic: Claude Code, Codex, etc.).
4. Reruns the suite and compares scores. **Improved** = more passed, fewer
   critical/hallucination failures, or (tie) more grounded responses.
   **Worse** = fewer passed, more critical, hallucination regression, backend
   won't start, or harness crash.
5. Keeps improvements (commit if `auto_commit`), otherwise `git reset --hard`
   to the checkpoint (`rollback_on_worse`). No-improvement changes are also
   rolled back.

Safety guards (each stops the loop with a blocker):
- Agent touches `agent/test_cases/`, the evaluator/runner, AGENT.md, or
  GROUNDING_POLICY.md → rollback + hard stop (no test-weakening).
- Obsidian vault fingerprint (md count/size/mtime, `.obsidian` excluded)
  changes during a repair → hard stop.
- Same category still failing after `max_same_failure_attempts` repairs,
  agent CLI fails twice in a row, rollback fails, or backend can't start.
- If the agent CLI isn't on PATH, the run degrades to report-only and writes
  a blocker — nothing is faked.

Outputs per run: `reports/autopilot_latest.md`,
`reports/history/autopilot_<ts>.md`, `logs/autopilot_<ts>.json`, plus
appends to TEST_LOG.md / FAILURE_LOG.md / CHANGELOG_AGENT.md / BLOCKERS.md.

Rollback caveats: a rolled-back iteration also reverts the TEST_LOG/
FAILURE_LOG lines appended during that iteration's retest (the raw JSON in
`agent/logs/` always survives). If no repair is kept at all, the checkpoint
commit is soft-reset away so your uncommitted work returns exactly as it was.
