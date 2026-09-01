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
python agent/run_silvia_autopilot.py --auto-repair                 # full loop (defaults: 2 iters, 20 min)
python agent/run_silvia_autopilot.py --auto-repair --max-iterations 2 --max-runtime-minutes 15
```

**Hardened defaults** (all overridable via flags or `config.json`):

| Guard | Default | Flag |
|---|---|---|
| Max iterations | 2 | `--max-iterations` |
| Max wall-clock runtime | 20 min | `--max-runtime-minutes` |
| Stop after N non-improving rounds | 2 | `--stop-if-no-improvement-rounds` |
| Stop if a category resists N repairs | 2 | `--max-same-failure-attempts` |
| Per-repair coding-agent timeout | 600 s | `--coding-agent-timeout-seconds` |
| Per-run test-suite timeout | 600 s | `--test-timeout-seconds` |
| Cold-restart verify after a kept fix | on | `--no-fresh-backend-verify` |

The coding-agent timeout is additionally clamped to the remaining runtime
budget, so the loop always leaves time to write a report before the ceiling.

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

Safety guards (each stops the loop; the first two mark the run **UNSAFE**):
- Agent touches `agent/test_cases/`, `evaluate_results.py`, `run_tests.py`,
  the client/prompt generator, AGENT.md, or GROUNDING_POLICY.md → rollback +
  hard stop, run flagged **UNSAFE**. Detected two ways every iteration: git
  status **and** a content-hash snapshot of every protected file (catches
  edits git might not surface). Process exits with code 2.
- Obsidian vault note files change (md count/size/mtime fingerprint,
  `.obsidian`/`.trash`/`.git` excluded) during a repair → rollback + hard
  stop, flagged **UNSAFE**.
- **Fresh-backend verification:** after a kept fix, a self-started backend is
  cold-restarted and retested. If the fix regresses on a clean start (i.e. it
  only worked via warm auto-reload state), the kept commit is rolled back and
  the loop stops. Skipped when you started the backend yourself (the autopilot
  won't kill a server it doesn't own).
- Runtime ceiling, iteration ceiling, consecutive-no-improvement limit,
  same-category-attempt limit, agent CLI failing twice, rollback failure, or
  backend that can't start — each stops cleanly with a blocker.
- **Ctrl+C** produces a clean partial report (the in-progress iteration's
  state, a blocker noting possible uncommitted changes, and the latest score).
- If the agent CLI isn't on PATH, the run degrades to report-only and writes
  a blocker — nothing is faked.

`reports/autopilot_latest.md` is rewritten **after every iteration**, not just
at the end, so you can watch progress live (and it survives a Ctrl+C).

Outputs per run: `reports/autopilot_latest.md`,
`reports/history/autopilot_<ts>.md`, `logs/autopilot_<ts>.json`, plus
appends to TEST_LOG.md / FAILURE_LOG.md / CHANGELOG_AGENT.md / BLOCKERS.md.

Rollback caveats: a rolled-back iteration also reverts the TEST_LOG/
FAILURE_LOG lines appended during that iteration's retest (the raw JSON in
`agent/logs/` always survives). If no repair is kept at all, the checkpoint
commit is soft-reset away so your uncommitted work returns exactly as it was.
