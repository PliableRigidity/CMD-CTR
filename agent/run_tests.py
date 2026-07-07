"""SILVIA autonomous QA test runner.

Usage:
    python agent/run_tests.py            # run every test case
    python agent/run_tests.py --category latency
    python agent/run_tests.py --id hal-001

Requires the SILVIA backend to be running (python main.py, port 8000 by
default). If it is not reachable, every test is recorded as an honest
"silvia_unreachable" error — the runner NEVER fakes a pass.

Outputs:
    agent/logs/run_<timestamp>.json           raw machine-readable results
    agent/reports/latest_failure_report.md    human-readable failure report
    agent/reports/history/report_<ts>.md      archived copy of each report
    TEST_LOG.md / FAILURE_LOG.md              appended summary entries
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent
sys.path.insert(0, str(AGENT_DIR))

import evaluate_results  # noqa: E402
from silvia_client import SilviaClient, SilviaUnreachable  # noqa: E402

TEST_CASE_DIR = AGENT_DIR / "test_cases"
LOG_DIR = AGENT_DIR / "logs"
REPORT_DIR = AGENT_DIR / "reports"
HISTORY_DIR = REPORT_DIR / "history"
TEST_LOG_MD = REPO_ROOT / "TEST_LOG.md"
FAILURE_LOG_MD = REPO_ROOT / "FAILURE_LOG.md"

FIX_DIRECTIONS = {
    "possible_hallucination": (
        "Enforce GROUNDING_POLICY.md in the conversation path: retrieve "
        "Brain63/Obsidian context before answering project questions, and "
        "answer 'I don't have enough information' when retrieval is empty. "
        "Look at backend/app/services/conversation_service.py and "
        "backend/app/services/brain63_service.py."
    ),
    "hallucination": (
        "Same as possible_hallucination: ground the answer in retrieved "
        "notes or refuse. Do not let the LLM free-generate project facts."
    ),
    "missing_retrieval": (
        "Ensure project/knowledge questions trigger Brain63/memory retrieval "
        "and that retrieved note paths are attached to the response sources "
        "(backend/app/services/conversation_service.py, brain63_service.py)."
    ),
    "grounding": (
        "Attach retrieval evidence (sources or knowledge tool calls) to the "
        "response so answers are auditable."
    ),
    "missing_required_term": (
        "The answer omitted expected real content. Check whether retrieval "
        "returned the right notes and whether the prompt keeps them."
    ),
    "forbidden_term": (
        "The answer contained content it must not. Usually a hallucination — "
        "apply the grounding policy."
    ),
    "forbidden_pattern": (
        "Invented specifics (e.g. dates) for something not in the notes. "
        "Apply the grounding policy: no gap-filling."
    ),
    "text_latency": (
        "Profile the chat path: model selection/keep-alive in backend/config.py, "
        "fast-paths in conversation_service.py, Ollama health. Use the "
        "'show chat latency' command for per-stage timings."
    ),
    "speech_latency": (
        "Profile TTS: backend/app/api/voice.py synthesize path and "
        "backend/app/voice/ pipeline. Check GET /api/voice/latency history."
    ),
    "speech_latency_unmeasured": (
        "TTS could not be exercised at all — check the speech backend "
        "(Speaches/TTS engine) is configured and /api/voice/synthesize works."
    ),
    "voice_endpoint": (
        "A voice endpoint failed. Check backend/app/api/voice.py and voice "
        "service wiring in backend/app/core/application.py."
    ),
    "tool_mismatch": (
        "The expected deterministic tool was not invoked. Check command "
        "routing in conversation_service.py so the query maps to the tool "
        "instead of free-form LLM generation."
    ),
    "empty_response": (
        "Chat returned an empty answer — inspect server logs for exceptions "
        "in the conversation path."
    ),
    "error_response": (
        "The backend errored or was unreachable. Start SILVIA (python main.py) "
        "or fix the failing endpoint before re-running."
    ),
}


# ── test execution ───────────────────────────────────────────────────────


def load_test_cases(category: str | None = None,
                    test_id: str | None = None) -> list[dict]:
    cases: list[dict] = []
    for path in sorted(TEST_CASE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[warn] Skipping malformed test file {path.name}: {e}")
            continue
        for case in data:
            case.setdefault("category", path.stem)
            case["_file"] = path.name
            cases.append(case)
    if category:
        cases = [c for c in cases if c.get("category") == category]
    if test_id:
        cases = [c for c in cases if c.get("id") == test_id]
    return cases


def run_case(client: SilviaClient, case: dict, silvia_alive: bool) -> dict:
    """Execute one test case against the live backend. Never fakes results."""
    record: dict = {"error": None}

    if not silvia_alive:
        record["error"] = (
            "silvia_unreachable: backend not running at "
            f"{client.base_url} (start it with: python main.py)"
        )
        return record

    voice_check = case.get("voice_check")
    try:
        if voice_check == "status":
            res = client.voice_status()
            record.update(res)
            body = res.get("body") or {}
            # VoiceStatus model: available/stt_available/tts_available/…
            record["voice_ok"] = res["ok"] and body.get("available") is True
            record["voice_error"] = res.get("error") or (
                None if record["voice_ok"] else f"Unexpected /voice/status body: {body}"
            )
            record["answer"] = json.dumps(body)[:400]
        elif voice_check == "latency_metrics":
            res = client.voice_latency_metrics()
            record.update(res)
            record["voice_ok"] = res["ok"] and isinstance(res.get("body"), dict)
            record["voice_error"] = res.get("error")
            record["answer"] = json.dumps(res.get("body") or {})[:400]
        elif voice_check == "synthesize":
            text = case.get("tts_text", "Testing SILVIA speech output.")
            res = client.synthesize(text)
            record.update(res)
            record["voice_ok"] = res["ok"]
            record["voice_error"] = res.get("error")
            record["speech_start_seconds"] = (
                res["tts_latency_seconds"] if res["ok"] else None
            )
            record["speech_error"] = res.get("error")
            record["answer"] = (
                f"TTS produced {res['audio_bytes']} bytes in "
                f"{res['tts_latency_seconds']}s" if res["ok"] else ""
            )
        else:
            record = client.chat(case["question"])
            # Optional speech-start measurement: text latency + TTS of the
            # first part of the real answer (approximates time-to-first-audio).
            if case.get("max_speech_start_seconds") is not None:
                if record.get("answer") and not record.get("error"):
                    tts = client.synthesize(record["answer"][:200])
                    record["tts_latency_seconds"] = tts["tts_latency_seconds"]
                    if tts["ok"]:
                        record["speech_start_seconds"] = round(
                            record["text_latency_seconds"]
                            + tts["tts_latency_seconds"], 3)
                    else:
                        record["speech_start_seconds"] = None
                        record["speech_error"] = tts.get("error")
    except SilviaUnreachable as e:
        record["error"] = f"silvia_unreachable mid-run: {e}"
    except Exception as e:  # harness bug or unexpected shape — report honestly
        record["error"] = f"harness_exception: {type(e).__name__}: {e}"

    return record


# ── reporting ────────────────────────────────────────────────────────────


def build_failure_report(run: dict) -> str:
    results = run["results"]
    failed = [r for r in results if not r["evaluation"]["passed"]]
    critical = [
        r for r in failed
        if any(f["check"] in ("possible_hallucination", "error_response",
                              "forbidden_pattern", "forbidden_term")
               for f in r["evaluation"]["failures"])
    ]
    categories: dict[str, int] = {}
    for r in failed:
        for f in r["evaluation"]["failures"]:
            categories[f["check"]] = categories.get(f["check"], 0) + 1

    lines = [
        "# SILVIA Failure Report",
        "",
        f"- **Run timestamp:** {run['timestamp']}",
        f"- **Silvia reachable:** {run['silvia_alive']}",
        f"- **Tests run:** {len(results)}",
        f"- **Passed:** {len(results) - len(failed)}",
        f"- **Failed:** {len(failed)}",
        f"- **Critical failures:** {len(critical)} "
        "(hallucination / invented details / errors)",
        "",
        "## Failure categories",
        "",
    ]
    if categories:
        for check, count in sorted(categories.items(), key=lambda kv: -kv[1]):
            lines.append(f"- `{check}`: {count}")
    else:
        lines.append("- none 🎉")

    lines += ["", "## Failures", ""]
    if not failed:
        lines.append("All tests passed in this run.")
    for r in failed:
        case, rec, ev = r["case"], r["record"], r["evaluation"]
        lines += [
            f"### {case['id']} — {case.get('category', '?')}",
            "",
            f"- **Question:** {case.get('question', case.get('voice_check', '—'))}",
            f"- **Expected behaviour:** {case.get('expected_behavior', '—')}",
            f"- **Actual answer:** {(rec.get('answer') or '—')[:600]}",
            f"- **Retrieved sources / evidence:** "
            f"{', '.join(ev['grounding_evidence']) or 'none'}",
            f"- **Text latency:** {rec.get('text_latency_seconds', '—')}s"
            f" | **Speech start:** {rec.get('speech_start_seconds', '—')}s",
            f"- **Tool calls:** "
            f"{', '.join(c['tool'] for c in rec.get('tool_calls') or []) or 'none'}",
            "- **Failure reasons:**",
        ]
        for f in ev["failures"]:
            lines.append(f"  - `{f['check']}` — {f['reason']}")
        fix_checks = {f["check"] for f in ev["failures"]}
        lines.append("- **Recommended fix direction:**")
        for check in fix_checks:
            direction = FIX_DIRECTIONS.get(check)
            if direction:
                lines.append(f"  - {direction}")
        lines.append("")
    return "\n".join(lines) + "\n"


def append_markdown_log(path: Path, entry: str) -> None:
    header = ""
    if not path.exists():
        title = path.stem.replace("_", " ").title()
        header = f"# {title}\n\nAppended automatically by `agent/run_tests.py`.\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(header + entry)


def write_logs_and_reports(run: dict) -> Path:
    ts_compact = run["timestamp"].replace(":", "").replace("-", "").replace(" ", "_")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = LOG_DIR / f"run_{ts_compact}.json"
    raw_path.write_text(json.dumps(run, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    report = build_failure_report(run)
    (REPORT_DIR / "latest_failure_report.md").write_text(report, encoding="utf-8")
    (HISTORY_DIR / f"report_{ts_compact}.md").write_text(report, encoding="utf-8")

    results = run["results"]
    failed = [r for r in results if not r["evaluation"]["passed"]]
    summary = (
        f"\n## Run {run['timestamp']}\n\n"
        f"- Silvia reachable: {run['silvia_alive']}\n"
        f"- Tests: {len(results)} | Passed: {len(results) - len(failed)} "
        f"| Failed: {len(failed)}\n"
        f"- Raw log: `agent/logs/{raw_path.name}`\n"
        f"- Report: `agent/reports/latest_failure_report.md`\n"
    )
    for r in results:
        mark = "PASS" if r["evaluation"]["passed"] else "FAIL"
        lat = r["record"].get("text_latency_seconds")
        lat_s = f" ({lat}s)" if lat is not None else ""
        summary += f"  - [{mark}] {r['case']['id']} — {r['case'].get('question', r['case'].get('voice_check'))}{lat_s}\n"
    append_markdown_log(TEST_LOG_MD, summary)

    if failed:
        fail_entry = f"\n## Run {run['timestamp']} — {len(failed)} failure(s)\n\n"
        for r in failed:
            reasons = "; ".join(f["reason"] for f in r["evaluation"]["failures"])
            fail_entry += f"- **{r['case']['id']}** ({r['case'].get('category')}): {reasons}\n"
        append_markdown_log(FAILURE_LOG_MD, fail_entry)

    return raw_path


# ── main ─────────────────────────────────────────────────────────────────


def _app_port_from_env() -> str:
    """Resolve the backend port the same way backend/config.py does:
    APP_PORT env var, then the repo .env file, then 8000."""
    import os
    port = os.getenv("APP_PORT")
    if port:
        return port
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("APP_PORT="):
                return line.split("=", 1)[1].strip() or "8000"
    return "8000"


def load_config() -> dict:
    config: dict = {}
    for name in ("config.json", "config.example.json"):
        path = AGENT_DIR / name
        if path.exists():
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
                break
            except json.JSONDecodeError as e:
                print(f"[warn] {name} is malformed ({e}); using defaults.")
    # config.json wins; otherwise follow the backend's real APP_PORT.
    if not (AGENT_DIR / "config.json").exists():
        config["base_url"] = f"http://localhost:{_app_port_from_env()}"
    return config


def run_suite(category: str | None = None, test_id: str | None = None) -> dict:
    config = load_config()
    client = SilviaClient(
        base_url=config.get("base_url", "http://localhost:8000"),
        timeout=config.get("request_timeout_seconds", 90),
    )
    cases = load_test_cases(category, test_id)
    if not cases:
        print("No test cases matched.")
        return {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "silvia_alive": False, "results": []}

    silvia_alive = client.is_alive()
    if not silvia_alive:
        print(f"[error] SILVIA backend is NOT reachable at {client.base_url}.")
        print("        Start it with: python main.py — recording honest failures.")

    results = []
    for i, case in enumerate(cases, 1):
        label = case.get("question") or f"voice_check:{case.get('voice_check')}"
        print(f"[{i}/{len(cases)}] {case['id']}: {label[:70]}")
        record = run_case(client, case, silvia_alive)
        evaluation = evaluate_results.evaluate_case(case, record)
        status = "PASS" if evaluation["passed"] else "FAIL"
        print(f"         -> {status}"
              + ("" if evaluation["passed"]
                 else f" ({evaluation['failures'][0]['reason'][:100]})"))
        results.append({"case": case, "record": record, "evaluation": evaluation})

    run = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": client.base_url,
        "silvia_alive": silvia_alive,
        "results": results,
    }
    raw_path = write_logs_and_reports(run)

    failed = sum(1 for r in results if not r["evaluation"]["passed"])
    print(f"\nDone: {len(results)} tests, {len(results) - failed} passed, "
          f"{failed} failed.")
    print(f"Raw log:  {raw_path}")
    print(f"Report:   {REPORT_DIR / 'latest_failure_report.md'}")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SILVIA QA suite.")
    parser.add_argument("--category", help="Only run one category "
                        "(file stem, e.g. latency)")
    parser.add_argument("--id", help="Only run one test id")
    args = parser.parse_args()
    run_suite(args.category, args.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
