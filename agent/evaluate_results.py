"""Rule-based evaluator for SILVIA QA test results.

Deliberately simple and transparent: every check is a plain string/number
rule that can be read and audited in one pass. No LLM judge.

evaluate_case(case, record) -> {
    "passed": bool,
    "failures": [{"check": str, "reason": str}],
    "failure_type": str | None,   # first/primary failure category
    "grounding_evidence": [str],  # what counted as retrieval evidence
}

Supported test-case fields (all optional except id/category/question):
    requires_obsidian_retrieval  bool   — grounding evidence must exist
    must_include                 [str]  — every term must appear (case-insensitive)
    must_include_any             [str]  — at least one term must appear
    must_not_include             [str]  — no term may appear
    must_not_include_patterns    [str]  — no regex may match (case-insensitive)
    must_not_invent              bool   — if no grounding evidence, the answer
                                          must admit uncertainty instead of
                                          stating confident details
    max_text_latency_seconds     num    — wall-clock chat latency threshold
    max_speech_start_seconds     num    — text latency + TTS latency threshold
    expected_tools_any           [str]  — at least one captured tool call must
                                          contain one of these substrings
    voice_check                  str    — "status" | "synthesize" | "latency_metrics"
                                          (handled by the runner; evaluated here)
"""

from __future__ import annotations

import re

# Phrases that count as SILVIA honestly admitting it lacks information.
UNCERTAINTY_MARKERS = [
    "don't have", "do not have", "no information", "not enough information",
    "couldn't find", "could not find", "can't find", "cannot find",
    "no notes", "no note", "not aware", "doesn't exist", "does not exist",
    "no record", "unable to find", "don't know", "do not know",
    "not familiar", "no mention", "not mentioned", "nothing in",
    "no data", "unsure", "i'm not sure", "i am not sure",
    "no such project", "isn't a project", "is not a project",
    "not in my", "not found", "no deadline", "not recorded",
    "not documented", "nothing recorded", "isn't recorded",
    "is not recorded",
]

# Tool-call / source names that count as evidence SILVIA retrieved real
# knowledge (Obsidian/Brain63 vault, project memory, registries, KG).
GROUNDING_EVIDENCE_PATTERN = re.compile(
    r"brain63|obsidian|memory|knowledge|project|registry|vault|note",
    re.IGNORECASE,
)


def _contains(answer: str, term: str) -> bool:
    return term.lower() in answer.lower()


def collect_grounding_evidence(record: dict) -> list[str]:
    """List everything in the record that counts as retrieval evidence."""
    evidence: list[str] = []
    for src in record.get("sources") or []:
        label = src.get("source") or src.get("title") or src.get("url") or ""
        if label:
            evidence.append(f"source: {label}")
    for call in record.get("tool_calls") or []:
        name = call.get("tool", "")
        if GROUNDING_EVIDENCE_PATTERN.search(name + " " + call.get("detail", "")):
            evidence.append(f"tool: {name}")
    return evidence


def _admits_uncertainty(answer: str) -> bool:
    low = answer.lower()
    return any(marker in low for marker in UNCERTAINTY_MARKERS)


def evaluate_case(case: dict, record: dict) -> dict:
    failures: list[dict] = []
    answer = record.get("answer", "") or ""
    evidence = collect_grounding_evidence(record)

    def fail(check: str, reason: str) -> None:
        failures.append({"check": check, "reason": reason})

    # ── hard errors first ────────────────────────────────────────────────
    if record.get("error"):
        fail("error_response", f"Transport/server error: {record['error']}")
    elif case.get("voice_check"):
        # Voice checks: the runner stores endpoint results in the record.
        if not record.get("voice_ok"):
            fail("voice_endpoint",
                 record.get("voice_error") or "Voice endpoint check failed.")
    elif not answer.strip():
        fail("empty_response", "Answer was empty.")

    # ── content checks (only meaningful when we got an answer) ───────────
    if answer.strip():
        for term in case.get("must_include", []):
            if not _contains(answer, term):
                fail("missing_required_term", f"Answer does not mention '{term}'.")

        include_any = case.get("must_include_any", [])
        if include_any and not any(_contains(answer, t) for t in include_any):
            fail("missing_required_term",
                 f"Answer mentions none of: {', '.join(include_any)}.")

        for term in case.get("must_not_include", []):
            if _contains(answer, term):
                fail("forbidden_term", f"Answer contains forbidden term '{term}'.")

        for pattern in case.get("must_not_include_patterns", []):
            if re.search(pattern, answer, re.IGNORECASE):
                fail("forbidden_pattern",
                     f"Answer matches forbidden pattern /{pattern}/.")

        if case.get("must_not_invent") and not evidence:
            # No retrieval evidence: the only honest answer admits uncertainty.
            if not _admits_uncertainty(answer):
                fail(
                    "possible_hallucination",
                    "No retrieval evidence (no sources, no knowledge-tool calls) "
                    "but the answer states details confidently instead of "
                    "admitting it lacks information.",
                )

    # ── grounding ────────────────────────────────────────────────────────
    if case.get("requires_obsidian_retrieval") and not record.get("error"):
        if not evidence:
            fail(
                "missing_retrieval",
                "Test requires Obsidian/knowledge retrieval but the response "
                "carried no sources and no knowledge-related tool calls.",
            )

    # ── latency ──────────────────────────────────────────────────────────
    max_text = case.get("max_text_latency_seconds")
    text_latency = record.get("text_latency_seconds")
    if max_text is not None and text_latency is not None and text_latency > max_text:
        fail("text_latency",
             f"Text latency {text_latency:.2f}s exceeds limit {max_text}s.")

    max_speech = case.get("max_speech_start_seconds")
    if max_speech is not None and not record.get("error"):
        speech_start = record.get("speech_start_seconds")
        if speech_start is None:
            fail("speech_latency_unmeasured",
                 record.get("speech_error")
                 or "Speech-start latency could not be measured (TTS call failed "
                    "or was unavailable).")
        elif speech_start > max_speech:
            fail("speech_latency",
                 f"Speech start {speech_start:.2f}s exceeds limit {max_speech}s.")

    # ── tool usage ───────────────────────────────────────────────────────
    expected_tools = case.get("expected_tools_any", [])
    if expected_tools and not record.get("error"):
        called = [c.get("tool", "").lower() for c in record.get("tool_calls") or []]
        matched = any(
            exp.lower() in name for exp in expected_tools for name in called
        )
        if not matched:
            fail(
                "tool_mismatch",
                f"Expected a tool call containing one of {expected_tools}; "
                f"captured tool calls: {called or 'none'}.",
            )

    primary_type = None
    if failures:
        primary_type = case.get("failure_type") or failures[0]["check"]

    return {
        "passed": not failures,
        "failures": failures,
        "failure_type": primary_type,
        "grounding_evidence": evidence,
    }
