from __future__ import annotations

import re


_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BULLET_RE = re.compile(r"^\s*[-*•]\s*", re.MULTILINE)
_JSONISH_RE = re.compile(r"^[\[\{].*[\]\}]$", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_for_speech(text: str) -> str:
    """Convert assistant text into something natural and safe to read aloud."""
    if not text:
        return ""

    cleaned = text.strip()
    if _JSONISH_RE.match(cleaned):
        return "I have the result ready."

    cleaned = _CODE_FENCE_RE.sub(" ", cleaned)
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _URL_RE.sub("the referenced website", cleaned)
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("*", "")
    cleaned = cleaned.replace("#", "")
    cleaned = cleaned.replace("|", ", ")
    cleaned = cleaned.replace("->", "to")
    cleaned = cleaned.replace("=>", "to")
    cleaned = cleaned.replace("&", "and")
    cleaned = _BULLET_RE.sub("", cleaned)
    cleaned = cleaned.replace("\n", " ")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip(" ,;")

    if len(cleaned) > 320:
        sentence_match = re.match(r"(.+?[.!?])(?:\s|$)", cleaned)
        if sentence_match:
            cleaned = sentence_match.group(1).strip()
        else:
            cleaned = cleaned[:320].rsplit(" ", 1)[0].strip() + "."

    return cleaned
