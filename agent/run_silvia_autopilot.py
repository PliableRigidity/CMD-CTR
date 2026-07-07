"""SILVIA QA autopilot v2 — autonomous test -> repair -> retest loop.

Usage:
    python agent/run_silvia_autopilot.py --report-only
        Run tests, generate failure report + repair prompt, write an
        autopilot report. No git operations, no coding agent.

    python agent/run_silvia_autopilot.py --auto-repair --max-iterations 5
        Full loop: for each iteration, create a git checkpoint, generate a
        repair prompt, invoke the configured coding agent, rerun the tests,
        and keep the change only if results improved (rollback otherwise).

Safety design (see AGENT.md):
    - Git checkpoint commit before every repair; hard rollback on worse or
      no-improvement results.
    - The harness itself is protected: if the coding agent touches
      agent/test_cases/, the evaluator, the runner, AGENT.md, or
      GROUNDING_POLICY.md, the iteration is rolled back and the loop stops.
    - The Obsidian vault is fingerprinted (md file count/size/mtime) before
      and after each repair; any change stops the loop with a loud blocker.
    - Results are parsed from the runner's raw JSON logs — never synthesized.
    - runtime logs/ are excluded from autopilot commits (they can contain
      tokens); rollbacks preserve agent/logs and agent/reports.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent
sys.path.insert(0, str(AGENT_DIR))

# Windows consoles default to cp1252; agent output can contain arbitrary
# Unicode. Never let a progress print crash the loop.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass

import generate_repair_prompt  # noqa: E402
from run_tests import _app_port_from_env  # noqa: E402

REPORT_DIR = AGENT_DIR / "reports"
HISTORY_DIR = REPORT_DIR / "history"
LOG_DIR = AGENT_DIR / "logs"

CRITICAL_CHECKS = {"possible_hallucination", "forbidden_pattern",
                   "forbidden_term", "error_response"}
HALLUCINATION_CHECKS = {"possible_hallucination", "forbidden_pattern",
                        "forbidden_term"}

# Files the coding agent must never change. Changing tests/evaluator to make
# the score go up is cheating; changes here trigger rollback + hard stop.
PROTECTED_PATHS = (
    "agent/test_cases/",
    "agent/evaluate_results.py",
    "agent/run_tests.py",
    "agent/silvia_client.py",
    "agent/generate_repair_prompt.py",
    "agent/run_silvia_autopilot.py",
    "AGENT.md",
    "GROUNDING_POLICY.md",
)

DEFAULTS = {
    "backend_start_command": "python main.py",
    "backend_start_timeout_seconds": 150,
    "test_command": "python agent/run_tests.py",
    "test_timeout_seconds": 900,
    "repair_prompt_path": "agent/reports/latest_repair_prompt.md",
    "coding_agent_command": "claude",
    "coding_agent_args": ["-p", "--permission-mode", "acceptEdits"],
    "coding_agent_timeout_seconds": 1800,
    "max_iterations": 5,
    "max_same_failure_attempts": 3,
    "auto_commit": True,
    "rollback_on_worse": True,
    "request_timeout_seconds": 90,
}

PROMPT_ADDENDUM = """
---

## Autopilot execution notes (added by run_silvia_autopilot.py)

- You are being invoked headlessly by the QA autopilot. Work non-interactively.
- The SILVIA backend is already running with auto-reload; do NOT start, stop,
  or restart servers, and do NOT run the test harness yourself — the autopilot
  reruns `python agent/run_tests.py` after you finish and decides keep/rollback.
- Do NOT modify anything under `agent/` or the root policy files
  (AGENT.md, GROUNDING_POLICY.md). Such changes are detected and auto-rolled
  back, and the whole run is aborted.
- Do NOT touch the Obsidian vault (BRAIN63_VAULT_PATH); it is fingerprinted.
- Make the smallest safe fix for the highest-priority failures first
  (hallucination/fabrication, then grounding evidence, then tool routing,
  then latency). It is fine to fix only a subset well.
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ts_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _git(*args: str, timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def load_config() -> dict:
    config = dict(DEFAULTS)
    for name in ("config.example.json", "config.json"):
        path = AGENT_DIR / name
        if path.exists():
            try:
                config.update(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as e:
                print(f"[warn] {name} malformed ({e}); ignoring.", flush=True)
    if not config.get("base_url"):
        config["base_url"] = f"http://localhost:{_app_port_from_env()}"
    return config


def _vault_path() -> str | None:
    p = os.getenv("BRAIN63_VAULT_PATH")
    if p:
        return p
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("BRAIN63_VAULT_PATH="):
                return line.split("=", 1)[1].strip() or None
    cfg = REPO_ROOT / "backend" / "config.py"
    if cfg.exists():
        m = re.search(r'"BRAIN63_VAULT_PATH",\s*r?"([^"]+)"',
                      cfg.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return None


def vault_fingerprint() -> tuple | None:
    """Cheap change detector for the vault: (md_count, total_size, max_mtime).
    Skips .obsidian/.trash/.git (the Obsidian app writes there on its own)."""
    path = _vault_path()
    if not path or not Path(path).is_dir():
        return None
    count, size, latest = 0, 0, 0.0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in (".obsidian", ".trash", ".git")]
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            try:
                st = os.stat(os.path.join(root, name))
            except OSError:
                continue
            count += 1
            size += st.st_size
            latest = max(latest, st.st_mtime)
    return (count, size, round(latest, 2))


# ── score parsing ────────────────────────────────────────────────────────


def parse_score(run_file: Path) -> dict:
    data = json.loads(run_file.read_text(encoding="utf-8"))
    results = data.get("results", [])
    passed_ids, failed_ids = [], []
    failed_categories: dict[str, int] = {}
    critical = hallucination = grounded = 0
    for r in results:
        case, ev = r["case"], r["evaluation"]
        if ev.get("grounding_evidence"):
            grounded += 1
        if ev["passed"]:
            passed_ids.append(case["id"])
            continue
        failed_ids.append(case["id"])
        cat = case.get("category", "unknown")
        failed_categories[cat] = failed_categories.get(cat, 0) + 1
        checks = {f["check"] for f in ev["failures"]}
        if checks & CRITICAL_CHECKS:
            critical += 1
        if checks & HALLUCINATION_CHECKS:
            hallucination += 1
    return {
        "run_file": run_file.name,
        "timestamp": data.get("timestamp"),
        "silvia_alive": data.get("silvia_alive", False),
        "total": len(results),
        "passed": len(passed_ids),
        "failed": len(failed_ids),
        "critical": critical,
        "hallucination": hallucination,
        "grounded_count": grounded,
        "passed_ids": passed_ids,
        "failed_ids": failed_ids,
        "failed_categories": failed_categories,
        "id_categories": {r["case"]["id"]: r["case"].get("category", "?")
                          for r in results},
    }


def compare_scores(before: dict, after: dict) -> tuple[str, list[str]]:
    """Return ('improved'|'worse'|'no_change', reasons)."""
    reasons: list[str] = []

    if not after["silvia_alive"]:
        return "worse", ["Backend was not reachable during the retest."]
    if after["passed"] < before["passed"]:
        reasons.append(f"Passed dropped {before['passed']} -> {after['passed']}.")
    if after["critical"] > before["critical"]:
        reasons.append(f"Critical failures rose {before['critical']} -> "
                       f"{after['critical']}.")
    regressed = [
        tid for tid in before["passed_ids"]
        if tid in after["failed_ids"]
        and after["id_categories"].get(tid) == "hallucination"
    ]
    if regressed:
        reasons.append(f"Hallucination tests regressed: {', '.join(regressed)}.")
    if reasons:
        return "worse", reasons

    if after["passed"] > before["passed"]:
        reasons.append(f"Passed rose {before['passed']} -> {after['passed']}.")
    if after["failed"] < before["failed"]:
        reasons.append(f"Failed dropped {before['failed']} -> {after['failed']}.")
    if after["critical"] < before["critical"]:
        reasons.append(f"Critical dropped {before['critical']} -> "
                       f"{after['critical']}.")
    if after["hallucination"] < before["hallucination"]:
        reasons.append(f"Hallucination failures dropped "
                       f"{before['hallucination']} -> {after['hallucination']}.")
    if not reasons and after["grounded_count"] > before["grounded_count"]:
        reasons.append(f"Grounding evidence improved "
                       f"{before['grounded_count']} -> "
                       f"{after['grounded_count']} grounded responses.")
    if reasons:
        return "improved", reasons
    return "no_change", ["No score dimension improved."]


# ── autopilot ────────────────────────────────────────────────────────────


class Autopilot:
    def __init__(self, config: dict, max_iterations: int, report_only: bool):
        self.config = config
        self.max_iterations = max_iterations
        self.report_only = report_only
        self.base_url = config["base_url"].rstrip("/")
        self.backend_proc: subprocess.Popen | None = None
        self.backend_external = False
        self.original_head: str | None = None
        self.first_checkpoint: str | None = None
        self.kept_commits: list[str] = []
        self.blockers: list[str] = []
        self.iterations: list[dict] = []
        self.baseline: dict | None = None
        self.final_score: dict | None = None
        self.stop_reason = ""
        self.category_streak: dict[str, int] = {}
        self.agent_failures_in_a_row = 0

    # ── backend ──────────────────────────────────────────────────────────

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=3) as r:
                return r.status == 200
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            return False

    def _wait_healthy(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._healthy():
                return True
            time.sleep(3)
        return False

    def ensure_backend(self) -> bool:
        if self._healthy():
            self.backend_external = True
            print(f"[backend] already running at {self.base_url}", flush=True)
            return True
        print(f"[backend] not running -> starting: "
              f"{self.config['backend_start_command']}", flush=True)
        log_path = LOG_DIR / f"autopilot_backend_{_ts_compact()}.log"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.backend_proc = subprocess.Popen(
            self.config["backend_start_command"], shell=True, cwd=REPO_ROOT,
            stdout=log_path.open("w", encoding="utf-8", errors="replace"),
            stderr=subprocess.STDOUT,
        )
        ok = self._wait_healthy(self.config["backend_start_timeout_seconds"])
        print(f"[backend] {'healthy' if ok else 'FAILED to become healthy'} "
              f"(log: {log_path.name})", flush=True)
        return ok

    def stop_backend_if_started(self) -> None:
        if self.backend_proc is None or self.backend_external:
            return
        print("[backend] stopping backend started by autopilot", flush=True)
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.backend_proc.pid),
                                "/T", "/F"], capture_output=True, timeout=30)
            else:
                self.backend_proc.terminate()
        except Exception as e:
            print(f"[backend] stop failed: {e}", flush=True)

    # ── tests ────────────────────────────────────────────────────────────

    def run_harness(self) -> dict | None:
        """Run the test suite as a subprocess; parse the new raw run JSON.
        Returns None on harness crash (nonzero exit or no run file)."""
        before = set(LOG_DIR.glob("run_*.json"))
        print(f"[tests] {self.config['test_command']}", flush=True)
        try:
            proc = subprocess.run(
                self.config["test_command"], shell=True, cwd=REPO_ROOT,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace",
                timeout=self.config["test_timeout_seconds"],
            )
        except subprocess.TimeoutExpired:
            print("[tests] TIMED OUT — treating as harness crash", flush=True)
            return None
        new = sorted(set(LOG_DIR.glob("run_*.json")) - before)
        if proc.returncode != 0 or not new:
            tail = (proc.stdout or "")[-1500:] + (proc.stderr or "")[-500:]
            print(f"[tests] harness crash (rc={proc.returncode}, "
                  f"new logs={len(new)}):\n{tail}", flush=True)
            return None
        score = parse_score(new[-1])
        print(f"[tests] {score['passed']}/{score['total']} passed, "
              f"{score['critical']} critical, "
              f"{score['hallucination']} hallucination, "
              f"{score['grounded_count']} grounded", flush=True)
        return score

    # ── git ──────────────────────────────────────────────────────────────

    def make_checkpoint(self, iteration: int) -> str | None:
        rc, dirty = _git("status", "--porcelain")
        if rc != 0:
            return None
        if dirty.strip():
            _git("add", "-A")
            _git("reset", "-q", "--", "logs")  # runtime logs may hold tokens
            rc_diff, _ = _git("diff", "--cached", "--quiet")
            if rc_diff == 1:  # staged changes exist
                rc_c, out = _git(
                    "commit", "-m",
                    f"autopilot: checkpoint before iteration {iteration} "
                    "(includes any pre-existing uncommitted work)")
                if rc_c != 0:
                    print(f"[git] checkpoint commit failed: {out}", flush=True)
                    return None
        rc, head = _git("rev-parse", "HEAD")
        if rc != 0:
            return None
        if self.first_checkpoint is None:
            self.first_checkpoint = head
        return head

    @staticmethod
    def changed_files() -> list[str]:
        rc, out = _git("status", "--porcelain")
        files = []
        for line in out.splitlines():
            path = line[3:].strip().strip('"')
            if " -> " in path:
                path = path.split(" -> ")[-1]
            files.append(path.replace("\\", "/"))
        return files

    @staticmethod
    def protected_violations(files: list[str]) -> list[str]:
        return [f for f in files
                if any(f == p or f.startswith(p) for p in PROTECTED_PATHS)]

    def rollback(self, checkpoint: str) -> bool:
        print(f"[git] rolling back to {checkpoint[:10]}", flush=True)
        rc1, out1 = _git("reset", "--hard", checkpoint)
        rc2, out2 = _git("clean", "-fd", "-e", "agent/logs",
                         "-e", "agent/reports", "-e", "logs")
        ok = rc1 == 0 and rc2 == 0
        if not ok:
            print(f"[git] ROLLBACK FAILED: {out1} {out2}", flush=True)
        return ok

    def commit_kept(self, iteration: int, summary: str) -> str | None:
        _git("add", "-A")
        _git("reset", "-q", "--", "logs")
        rc_diff, _ = _git("diff", "--cached", "--quiet")
        if rc_diff != 1:
            return None  # nothing to commit
        rc, out = _git("commit", "-m",
                       f"autopilot: iteration {iteration} repair kept — {summary}")
        if rc != 0:
            print(f"[git] kept-commit failed: {out}", flush=True)
            return None
        rc, head = _git("rev-parse", "HEAD")
        return head if rc == 0 else None

    def unwind_checkpoint_if_unused(self) -> None:
        """If nothing was kept, soft-reset the checkpoint commit so the
        user's pre-existing uncommitted work returns to its original state."""
        if (self.report_only or self.kept_commits or
                not self.first_checkpoint or not self.original_head or
                self.first_checkpoint == self.original_head):
            return
        rc, head = _git("rev-parse", "HEAD")
        if rc == 0 and head == self.first_checkpoint:
            print("[git] no repairs kept -> unwinding checkpoint commit "
                  "(soft reset, files preserved)", flush=True)
            _git("reset", "--soft", self.original_head)
            _git("reset", "-q")

    # ── coding agent ─────────────────────────────────────────────────────

    def agent_command(self) -> tuple[list[str] | None, str | None]:
        cmd = self.config.get("coding_agent_command")
        if not cmd:
            return None, "No coding_agent_command configured."
        exe = shutil.which(cmd)
        if exe is None:
            return None, (f"Coding agent CLI '{cmd}' not found on PATH — "
                          "cannot auto-repair in this environment.")
        return [exe] + list(self.config.get("coding_agent_args", [])), None

    def invoke_agent(self, prompt_path: Path) -> tuple[bool, str]:
        cmd, err = self.agent_command()
        if cmd is None:
            return False, err or "agent unavailable"
        print(f"[agent] invoking: {' '.join(cmd)} < {prompt_path.name} "
              f"(timeout {self.config['coding_agent_timeout_seconds']}s)",
              flush=True)
        try:
            with prompt_path.open("r", encoding="utf-8") as f:
                proc = subprocess.run(
                    cmd, stdin=f, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", cwd=REPO_ROOT,
                    timeout=self.config["coding_agent_timeout_seconds"],
                )
        except subprocess.TimeoutExpired:
            return False, "Coding agent timed out."
        except OSError as e:
            return False, f"Coding agent failed to launch: {e}"
        tail = ((proc.stdout or "")[-2000:] + "\n" +
                (proc.stderr or "")[-500:]).strip()
        print(f"[agent] exit code {proc.returncode}; output tail:\n"
              f"{tail[-800:]}", flush=True)
        return proc.returncode == 0, tail

    def generate_prompt(self) -> Path:
        generate_repair_prompt.main()
        prompt_path = REPO_ROOT / self.config["repair_prompt_path"]
        _append(prompt_path, PROMPT_ADDENDUM)
        return prompt_path

    # ── main loop ────────────────────────────────────────────────────────

    def run(self) -> None:
        started = _now()
        rc, head = _git("rev-parse", "HEAD")
        self.original_head = head if rc == 0 else None

        try:
            if not self.ensure_backend():
                self.stop_reason = "Backend could not start."
                self.blockers.append(
                    "Backend failed to become healthy at "
                    f"{self.base_url} within "
                    f"{self.config['backend_start_timeout_seconds']}s — see "
                    "agent/logs/autopilot_backend_*.log.")
                return

            self.baseline = self.run_harness()
            if self.baseline is None:
                self.stop_reason = "Test harness crashed on the baseline run."
                self.blockers.append(self.stop_reason)
                return
            self.final_score = self.baseline

            self.generate_prompt()

            if self.report_only:
                self.stop_reason = "Report-only mode (no repair attempted)."
                return

            cmd, err = self.agent_command()
            if cmd is None:
                self.stop_reason = ("Coding agent unavailable — staying in "
                                    "report-only mode.")
                self.blockers.append(err or "coding agent unavailable")
                return

            prev = self.baseline
            for i in range(1, self.max_iterations + 1):
                print(f"\n===== Iteration {i}/{self.max_iterations} =====",
                      flush=True)
                if prev["failed"] == 0:
                    self.stop_reason = "All tests pass."
                    break
                if prev["critical"] == 0:
                    self.stop_reason = "No critical failures remain."
                    break
                over = [c for c, n in self.category_streak.items()
                        if n >= self.config["max_same_failure_attempts"]]
                if over:
                    self.stop_reason = (
                        f"Category '{over[0]}' still failing after "
                        f"{self.config['max_same_failure_attempts']} repair "
                        "attempts — human review needed.")
                    self.blockers.append(self.stop_reason)
                    break

                record: dict = {"iteration": i, "kept": False, "commit": None,
                                "files_changed": [], "verdict": None,
                                "reasons": [], "notes": []}
                self.iterations.append(record)

                checkpoint = self.make_checkpoint(i)
                if checkpoint is None:
                    self.stop_reason = "Git checkpoint failed."
                    self.blockers.append(self.stop_reason)
                    break
                record["checkpoint"] = checkpoint

                prompt_path = self.generate_prompt()
                vault_before = vault_fingerprint()

                agent_ok, agent_tail = self.invoke_agent(prompt_path)
                record["agent_ok"] = agent_ok
                record["agent_output_tail"] = agent_tail[-1000:]
                if not agent_ok:
                    self.agent_failures_in_a_row += 1
                    record["notes"].append("Coding agent invocation failed.")
                    self.rollback(checkpoint)
                    if self.agent_failures_in_a_row >= 2:
                        self.stop_reason = ("Coding agent failed twice in a "
                                            "row.")
                        self.blockers.append(
                            f"{self.stop_reason} Last output: "
                            f"{agent_tail[-300:]}")
                        break
                    continue
                self.agent_failures_in_a_row = 0

                record["files_changed"] = self.changed_files()

                violations = self.protected_violations(record["files_changed"])
                if violations:
                    record["notes"].append(
                        f"PROTECTED FILES MODIFIED: {', '.join(violations)}")
                    self.blockers.append(
                        "Coding agent modified protected harness/test files "
                        f"({', '.join(violations)}). Iteration rolled back; "
                        "loop stopped. Human review required.")
                    if not self.rollback(checkpoint):
                        self.blockers.append("Rollback after protected-file "
                                             "violation FAILED.")
                    self.stop_reason = "Protected files modified by agent."
                    break

                vault_after = vault_fingerprint()
                if vault_before is not None and vault_after != vault_before:
                    self.blockers.append(
                        "OBSIDIAN VAULT CHANGED during repair iteration "
                        f"{i} (fingerprint {vault_before} -> {vault_after}). "
                        "The autopilot cannot roll back vault files. Repo "
                        "changes were rolled back; loop stopped. Verify the "
                        "vault manually (or confirm the change was yours).")
                    self.rollback(checkpoint)
                    self.stop_reason = "Obsidian vault changed during repair."
                    break

                if not self._wait_healthy(60):
                    record["verdict"] = "worse"
                    record["reasons"] = ["Backend no longer healthy after "
                                         "repair (reload failed)."]
                    if self.config["rollback_on_worse"]:
                        if not self.rollback(checkpoint):
                            self.stop_reason = "Rollback failed."
                            self.blockers.append(self.stop_reason)
                            break
                        if not self._wait_healthy(60):
                            self.stop_reason = ("Backend unhealthy even after "
                                                "rollback.")
                            self.blockers.append(self.stop_reason)
                            break
                    self._bump_streaks(prev)
                    continue

                after = self.run_harness()
                if after is None:
                    record["verdict"] = "worse"
                    record["reasons"] = ["Test harness crashed after repair."]
                    if not self.rollback(checkpoint):
                        self.blockers.append("Rollback after harness crash "
                                             "FAILED.")
                    self.stop_reason = "Test harness crashed after repair."
                    self.blockers.append(self.stop_reason)
                    break

                verdict, reasons = compare_scores(prev, after)
                record["verdict"] = verdict
                record["reasons"] = reasons
                record["score_after"] = {k: after[k] for k in
                                         ("passed", "failed", "critical",
                                          "hallucination", "grounded_count")}
                print(f"[compare] {verdict}: {'; '.join(reasons)}", flush=True)

                if verdict == "improved":
                    record["kept"] = True
                    self.final_score = after
                    summary = "; ".join(reasons)[:100]
                    if self.config["auto_commit"]:
                        commit = self.commit_kept(i, summary)
                        record["commit"] = commit
                        if commit:
                            self.kept_commits.append(commit)
                    else:
                        self.kept_commits.append("(uncommitted)")
                    _append(REPO_ROOT / "CHANGELOG_AGENT.md",
                            f"\n## {_now()} — autopilot iteration {i} kept\n\n"
                            f"- {summary}\n"
                            f"- Files: {', '.join(record['files_changed'][:15]) or 'none'}\n"
                            f"- Commit: {record['commit'] or 'not committed'}\n")
                    prev = after
                else:
                    reason_txt = "; ".join(reasons)
                    record["notes"].append(f"Rolled back ({verdict}): "
                                           f"{reason_txt}")
                    if self.config["rollback_on_worse"]:
                        if not self.rollback(checkpoint):
                            self.stop_reason = "Rollback failed."
                            self.blockers.append(self.stop_reason)
                            break
                        self._wait_healthy(60)
                    else:
                        record["notes"].append("rollback_on_worse disabled — "
                                               "changes left in tree.")

                self._bump_streaks(prev)

            if not self.stop_reason:
                self.stop_reason = (f"Max iterations "
                                    f"({self.max_iterations}) reached.")
        finally:
            self.unwind_checkpoint_if_unused()
            self.stop_backend_if_started()
            self.write_outputs(started)

    def _bump_streaks(self, score: dict) -> None:
        for cat in list(self.category_streak):
            if cat not in score["failed_categories"]:
                self.category_streak[cat] = 0
        for cat in score["failed_categories"]:
            self.category_streak[cat] = self.category_streak.get(cat, 0) + 1

    # ── reporting ────────────────────────────────────────────────────────

    def write_outputs(self, started: str) -> None:
        ts = _ts_compact()
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        def fmt(s: dict | None) -> str:
            if not s:
                return "n/a (harness did not produce a score)"
            return (f"{s['passed']}/{s['total']} passed, {s['failed']} failed, "
                    f"{s['critical']} critical, {s['hallucination']} "
                    f"hallucination, {s['grounded_count']} grounded")

        lines = [
            "# SILVIA Autopilot Report",
            "",
            f"- **Started:** {started}",
            f"- **Finished:** {_now()}",
            f"- **Mode:** {'report-only' if self.report_only else 'auto-repair'}",
            f"- **Start score:** {fmt(self.baseline)}",
            f"- **End score:** {fmt(self.final_score)}",
            f"- **Iterations run:** {len(self.iterations)}",
            f"- **Repairs kept:** {sum(1 for r in self.iterations if r['kept'])}",
            f"- **Repairs rolled back:** "
            f"{sum(1 for r in self.iterations if not r['kept'])}",
            f"- **Critical failures before/after:** "
            f"{self.baseline['critical'] if self.baseline else '?'} -> "
            f"{self.final_score['critical'] if self.final_score else '?'}",
            f"- **Kept commits:** {', '.join(self.kept_commits) or 'none'}",
            f"- **Stop reason:** {self.stop_reason}",
            "",
        ]
        if self.final_score:
            lines += ["## Remaining failures", ""]
            if self.final_score["failed_ids"]:
                for tid in self.final_score["failed_ids"]:
                    cat = self.final_score["id_categories"].get(tid, "?")
                    lines.append(f"- {tid} ({cat})")
            else:
                lines.append("- none")
            lines.append("")
        if self.iterations:
            lines += ["## Iterations", ""]
            for r in self.iterations:
                lines += [
                    f"### Iteration {r['iteration']} — "
                    f"{'KEPT' if r['kept'] else 'rolled back / failed'}",
                    "",
                    f"- Checkpoint: {r.get('checkpoint', 'n/a')}",
                    f"- Agent invocation ok: {r.get('agent_ok', 'n/a')}",
                    f"- Verdict: {r.get('verdict', 'n/a')} — "
                    f"{'; '.join(r.get('reasons', [])) or 'n/a'}",
                    f"- Files changed: "
                    f"{', '.join(r['files_changed'][:20]) or 'none'}",
                    f"- Commit: {r.get('commit') or 'none'}",
                ]
                for note in r["notes"]:
                    lines.append(f"- Note: {note}")
                lines.append("")
        lines += ["## Blockers", ""]
        if self.blockers:
            lines += [f"- {b}" for b in self.blockers]
        else:
            lines.append("- none")
        report = "\n".join(lines) + "\n"

        (REPORT_DIR / "autopilot_latest.md").write_text(report, encoding="utf-8")
        (HISTORY_DIR / f"autopilot_{ts}.md").write_text(report, encoding="utf-8")
        (LOG_DIR / f"autopilot_{ts}.json").write_text(json.dumps({
            "started": started, "finished": _now(),
            "mode": "report-only" if self.report_only else "auto-repair",
            "config": {k: v for k, v in self.config.items() if k != "notes"},
            "baseline": self.baseline, "final": self.final_score,
            "iterations": self.iterations, "kept_commits": self.kept_commits,
            "blockers": self.blockers, "stop_reason": self.stop_reason,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

        _append(REPO_ROOT / "TEST_LOG.md",
                f"\n## Autopilot run {started}\n\n"
                f"- Mode: {'report-only' if self.report_only else 'auto-repair'}"
                f" | Start: {fmt(self.baseline)} | End: {fmt(self.final_score)}\n"
                f"- Iterations: {len(self.iterations)} | Kept: "
                f"{sum(1 for r in self.iterations if r['kept'])} | "
                f"Stop: {self.stop_reason}\n"
                f"- Report: `agent/reports/autopilot_latest.md`\n")
        if self.final_score and self.final_score["failed_ids"]:
            _append(REPO_ROOT / "FAILURE_LOG.md",
                    f"\n## Autopilot run {started} — "
                    f"{self.final_score['failed']} failure(s) remain\n\n"
                    + "".join(f"- {tid} "
                              f"({self.final_score['id_categories'].get(tid, '?')})\n"
                              for tid in self.final_score["failed_ids"]))
        if self.blockers:
            _append(REPO_ROOT / "BLOCKERS.md",
                    f"\n## Autopilot run {started}\n\n"
                    + "".join(f"- {b}\n" for b in self.blockers))

        print(f"\n[report] {REPORT_DIR / 'autopilot_latest.md'}", flush=True)
        print(f"[report] Start: {fmt(self.baseline)}", flush=True)
        print(f"[report] End:   {fmt(self.final_score)}", flush=True)
        print(f"[report] Stop reason: {self.stop_reason}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SILVIA autonomous QA + repair loop.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--auto-repair", action="store_true",
                      help="Run the full test->repair->retest loop.")
    mode.add_argument("--report-only", action="store_true",
                      help="Tests + reports + repair prompt only (default).")
    parser.add_argument("--max-iterations", type=int, default=None,
                        help="Override max repair iterations from config.")
    args = parser.parse_args()

    config = load_config()
    max_iterations = args.max_iterations or config["max_iterations"]
    report_only = not args.auto_repair

    pilot = Autopilot(config, max_iterations, report_only)
    pilot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
