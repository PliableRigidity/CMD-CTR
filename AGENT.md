# AGENT.md — Operating Manual for Coding Agents Working on SILVIA

This file is the contract for any AI coding agent (Claude, Codex, or other)
that modifies this repository. Read it fully before changing code.

## 1. What SILVIA is

SILVIA is a local-first AI assistant / command center (this repo, CMD-CTR):
FastAPI backend (`backend/`, runs on `http://localhost:8000` via
`python main.py`), React frontend (`frontend/`), local LLMs via Ollama, a
voice pipeline (STT/TTS/wake word), deterministic tool routing, and a
**read-only** connection to the user's Obsidian knowledge vault ("Brain63",
path in `backend/config.py` → `BRAIN63_VAULT_PATH`).

SILVIA's goal: answer questions about the user's projects, knowledge, and
systems **truthfully and grounded in real data**, execute deterministic tools
reliably, and respond fast enough for voice interaction.

Known problem areas the QA system targets: hallucinated project
details/statuses/deadlines, weak Obsidian grounding, slow chat responses,
delayed speech output, inconsistent tool usage.

## 2. The autonomous QA loop

```
run tests → evaluate → failure report → repair prompt → (human-approved fix)
    ↑                                                            │
    └────────────────────── retest ──────────────────────────────┘
```

Everything lives in `agent/`. Today the loop is human-in-the-loop: the
autopilot produces a repair prompt; a human hands it to a coding agent.
Auto-repair comes later (TODOs in `agent/run_silvia_autopilot.py`).

## 3. How to run tests

```bash
python main.py                      # terminal 1: start SILVIA
python agent/run_tests.py           # terminal 2: full suite
python agent/run_silvia_autopilot.py  # suite + report + repair prompt
```

Details and options: `agent/README.md`.

## 4. How to interpret failure reports

`agent/reports/latest_failure_report.md` lists, per failure: test id,
question, expected behaviour, actual answer, retrieval evidence, latency,
failure reasons (machine checks like `possible_hallucination`,
`missing_retrieval`, `text_latency`), and a recommended fix direction.
Raw data for the same run is in `agent/logs/run_<ts>.json`.

Priority order when fixing: hallucinations / invented facts first, then
grounding gaps, then tool routing, then latency.

`silvia_unreachable` failures mean the backend wasn't running — start it and
rerun before treating anything else as real.

## 5. How to generate repair prompts

```bash
python agent/generate_repair_prompt.py
```

Reads the latest failure report + run log, writes
`agent/reports/latest_repair_prompt.md` with scoped instructions and file
hints. Hand that file to the coding agent verbatim.

## 6. Hard rules for coding agents

1. **Do not invent project goals, deadlines, statuses, or memories** — in
   code, in docs, in commit messages, or in SILVIA's behavior.
2. **Do not modify the Obsidian vault** (`BRAIN63_VAULT_PATH`). It is
   read-only input. No writes, renames, or deletions — ever.
3. **Do not remove or disable working features** to make tests pass.
4. **Do not hide or fake failures.** Never weaken a test, hardcode an
   expected answer, or special-case QA session ids.
5. **Do not rewrite the whole project** or refactor beyond the failure being
   fixed, unless explicitly instructed by the human.
6. **Use small, testable fixes** — one failure category at a time.
7. **Run tests after changes** (`python agent/run_tests.py`) and report the
   real before/after numbers.
8. **Log every change** in `CHANGELOG_AGENT.md` (date, what, why, files).
9. If something can't be fixed safely, write it up in `BLOCKERS.md` and stop.

## 7. Stop conditions

Stop working and report to the human when:

- A fix would require touching the Obsidian vault or deleting a feature.
- Two consecutive fix attempts made results worse or no better.
- A fix requires architectural changes (new services, DB schema changes,
  replacing the LLM stack).
- Tests conflict with each other or with observed correct behavior
  (then propose a test change — don't silently edit test cases).
- Anything requires credentials, paid APIs, or network services not already
  in the repo.

## 8. Rollback / checkpoint recommendations

- Before fixing: ensure a clean `git status` or work on a branch
  (`git checkout -b qa-repair-<date>`); commit checkpoints per fix.
- After fixing: rerun the suite; if pass count dropped, `git revert`/reset the
  fix rather than stacking more changes on top.
- Never force-push, never rewrite history on `main`.

## 9. Do NOT modify without explicit human approval

- The Obsidian vault (outside this repo) — never, even with approval flows.
- `agent/test_cases/*.json` — tests define truth; changing them to pass is
  cheating. Propose changes in BLOCKERS.md instead.
- `AGENT.md`, `GROUNDING_POLICY.md` — the rules themselves.
- Database files under `data/`, `backend/config.py` defaults for vault path,
  safety framework (`backend/app/services/safety_*`, approval/workflow
  engines), and anything under `logs/`.
- Git history, remotes, or CI configuration.
