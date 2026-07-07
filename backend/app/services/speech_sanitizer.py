from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BULLET_RE = re.compile(r"^\s*[-*•]\s*", re.MULTILINE)
_JSONISH_RE = re.compile(r"^[\[\{].*[\]\}]$", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Maximum chars for TTS — keeps synthesis fast (Silero/local TTS is slow on long text)
VOICE_MAX_CHARS = 200


def sanitize_for_speech(text: str, max_sentences: int = 2) -> str:
    """Convert assistant text into short, natural spoken language.

    max_sentences: hard cap on number of sentences (default 2).
    Keep it low — TTS synthesis time scales linearly with text length.
    """
    if not text:
        return ""

    cleaned = text.strip()
    if _JSONISH_RE.match(cleaned):
        return "I have the result ready."

    cleaned = _CODE_FENCE_RE.sub(" ", cleaned)
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = _INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _URL_RE.sub("the referenced website", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("*", "").replace("#", "")
    cleaned = cleaned.replace("|", ", ").replace("->", "to").replace("=>", "to").replace("&", "and")
    cleaned = _BULLET_RE.sub("", cleaned)
    cleaned = cleaned.replace("\n", " ")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip(" ,;")

    # Always truncate to first N sentences — never send walls of text to TTS
    sentences = _SENTENCE_RE.split(cleaned)
    if len(sentences) > max_sentences:
        cleaned = " ".join(sentences[:max_sentences]).strip()
        if not cleaned.endswith((".", "!", "?")):
            cleaned += "."

    # Hard char cap — safety net for single very long sentences
    if len(cleaned) > VOICE_MAX_CHARS:
        cut = cleaned[:VOICE_MAX_CHARS].rsplit(" ", 1)[0].strip()
        if not cut.endswith((".", "!", "?")):
            cut += "."
        cleaned = cut

    return cleaned
