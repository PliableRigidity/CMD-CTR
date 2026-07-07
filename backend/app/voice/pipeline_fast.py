"""
SILVIA Fast Voice Pipeline — sentence-level streaming TTS architecture.

Architecture inspired by llm-voice-assistant (AGPL-3.0).
No code copied — design implemented independently.

Core insight: don't wait for the full LLM response before speaking.
Stream tokens → detect sentence boundaries → TTS each sentence immediately.
First audio starts while LLM is still generating the rest of the response.

Target: under 2 seconds to first audio.

Latency breakdown:
  STT:           time from audio capture to transcript
  LLM first tok: time from query submit to first token
  First sentence: time from query to first complete sentence
  TTS synthesis:  time to synthesize first sentence
  Playback start: total time to first audio

Components in this file:
  VoiceState        — canonical state enum for the voice state machine
  VoiceStateMachine — explicit state machine with valid transitions
  SentenceChunker   — buffers LLM tokens and emits complete sentences
  VoiceLatencyLogger — per-turn latency tracking (kept in memory, last N turns)
"""
from __future__ import annotations

import datetime
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterator, Optional


# ── State Machine ──────────────────────────────────────────────────────────────

class VoiceState(str, Enum):
    """Voice conversation lifecycle states.

    COOLDOWN is intentionally absent — it must not block follow-up conversation.
    Cooldown only prevents repeated wake-word firing in IDLE (handled in detector).
    """
    IDLE               = "idle"
    WAKE_LISTENING     = "wake_listening"
    RECORDING          = "recording"
    TRANSCRIBING       = "transcribing"
    THINKING           = "thinking"
    SPEAKING           = "speaking"
    FOLLOWUP_LISTENING = "followup_listening"
    INTERRUPTED        = "interrupted"
    ERROR              = "error"


_VALID_TRANSITIONS: dict[VoiceState, set[VoiceState]] = {
    VoiceState.IDLE:               {VoiceState.WAKE_LISTENING, VoiceState.ERROR},
    VoiceState.WAKE_LISTENING:     {VoiceState.RECORDING, VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.RECORDING:          {VoiceState.TRANSCRIBING, VoiceState.INTERRUPTED, VoiceState.ERROR},
    VoiceState.TRANSCRIBING:       {VoiceState.THINKING, VoiceState.WAKE_LISTENING, VoiceState.ERROR},
    VoiceState.THINKING:           {VoiceState.SPEAKING, VoiceState.FOLLOWUP_LISTENING, VoiceState.ERROR},
    VoiceState.SPEAKING:           {VoiceState.FOLLOWUP_LISTENING, VoiceState.INTERRUPTED, VoiceState.ERROR},
    VoiceState.FOLLOWUP_LISTENING: {VoiceState.RECORDING, VoiceState.IDLE, VoiceState.WAKE_LISTENING, VoiceState.ERROR},
    VoiceState.INTERRUPTED:        {VoiceState.FOLLOWUP_LISTENING, VoiceState.WAKE_LISTENING, VoiceState.ERROR},
    VoiceState.ERROR:              {VoiceState.IDLE},
}


class VoiceStateMachine:
    """Explicit state machine for the voice conversation lifecycle.

    Transitions are validated against _VALID_TRANSITIONS.
    force() allows recovery from stuck states.
    """

    def __init__(self) -> None:
        self._state = VoiceState.IDLE
        self._history: list[tuple[str, float]] = []

    @property
    def state(self) -> VoiceState:
        return self._state

    def transition(self, new_state: VoiceState, *, reason: str = "") -> bool:
        """Attempt a validated transition. Returns True on success."""
        allowed = _VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            return False
        self._history.append((f"{self._state.value}->{new_state.value}", time.monotonic()))
        self._state = new_state
        return True

    def force(self, new_state: VoiceState, *, reason: str = "forced") -> None:
        """Force a transition regardless of validity — for error recovery only."""
        self._history.append((f"FORCE:{self._state.value}->{new_state.value}:{reason}", time.monotonic()))
        self._state = new_state

    def history(self, last: int = 10) -> list[str]:
        return [h[0] for h in self._history[-last:]]


# ── Sentence Chunker ───────────────────────────────────────────────────────────

# Sentence endings: . ! ? optionally followed by closing quotes/brackets,
# then mandatory whitespace. This lets us detect "Hello." vs "U.S.A."
_SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])["\']?\s+')

# Characters to strip before sending to TTS
_MARKDOWN_NOISE = re.compile(r"\*\*|__|\*|#|`|~")


class SentenceChunker:
    """Buffer streaming LLM tokens and emit complete sentences.

    Architecture: inspired by llm-voice-assistant sentence chunking.
    Implementation is independent — no code shared.

    Usage:
        chunker = SentenceChunker(max_sentences=3)
        for token in llm_stream:
            sentences = chunker.feed(token)
            for s in sentences:
                await tts_queue.put(s)
        remainder = chunker.flush()
        if remainder:
            await tts_queue.put(remainder)
    """

    def __init__(self, max_sentences: int = 3) -> None:
        self._buf: list[str] = []
        self._max = max_sentences
        self._count = 0

    @property
    def sentences_emitted(self) -> int:
        return self._count

    @property
    def at_limit(self) -> bool:
        return self._count >= self._max

    def feed(self, token: str) -> list[str]:
        """Add a token; return any newly complete sentences (may be empty list)."""
        if self.at_limit:
            return []
        self._buf.append(token)
        return self._extract()

    def flush(self) -> Optional[str]:
        """Return any remaining buffered text at end-of-stream."""
        if not self._buf or self.at_limit:
            self._buf.clear()
            return None
        remaining = self._clean("".join(self._buf))
        self._buf.clear()
        if not remaining:
            return None
        self._count += 1
        return remaining

    def reset(self) -> None:
        self._buf.clear()
        self._count = 0

    def _extract(self) -> list[str]:
        current = "".join(self._buf)
        parts = _SENTENCE_BOUNDARY.split(current)

        if len(parts) <= 1:
            return []  # no complete sentence yet

        sentences: list[str] = []
        for part in parts[:-1]:
            if self.at_limit:
                break
            cleaned = self._clean(part)
            if cleaned:
                sentences.append(cleaned)
                self._count += 1

        # Rebuild buffer with unprocessed tail
        self._buf = [parts[-1]] if parts[-1] else []
        return sentences

    @staticmethod
    def _clean(text: str) -> str:
        text = _MARKDOWN_NOISE.sub("", text).strip()
        return text


# ── Latency Logger ─────────────────────────────────────────────────────────────

@dataclass
class VoiceTurnLatency:
    """Per-turn latency breakdown. All times in milliseconds from query start."""
    turn_id: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")

    # When did each pipeline stage complete?
    stt_ms: float = 0.0          # transcript received
    llm_first_token_ms: float = 0.0  # first LLM token
    first_sentence_ms: float = 0.0   # first sentence emitted by chunker
    tts_synthesis_ms: float = 0.0    # first sentence TTS complete (server-side)
    playback_start_ms: float = 0.0   # browser received + started first audio
    total_ms: float = 0.0

    sentences: int = 0
    response_chars: int = 0
    tts_chars: int = 0
    stt_provider: str = ""
    tts_provider: str = ""


class VoiceLatencyLogger:
    """Track per-turn voice pipeline latency. Stores the last max_history turns."""

    def __init__(self, max_history: int = 20) -> None:
        self._history: deque[VoiceTurnLatency] = deque(maxlen=max_history)
        self._active: Optional[VoiceTurnLatency] = None
        self._t0: float = 0.0

    # ── Turn lifecycle ──────────────────────────────────────────────────────

    def start_turn(self, turn_id: str, stt_provider: str = "", tts_provider: str = "") -> None:
        self._t0 = time.perf_counter()
        self._active = VoiceTurnLatency(
            turn_id=turn_id,
            stt_provider=stt_provider,
            tts_provider=tts_provider,
        )

    def mark_stt(self) -> None:
        if self._active:
            self._active.stt_ms = self._elapsed()

    def mark_first_token(self) -> None:
        if self._active:
            self._active.llm_first_token_ms = self._elapsed()

    def mark_first_sentence(self, chars: int = 0) -> None:
        if self._active:
            self._active.first_sentence_ms = self._elapsed()
            self._active.tts_chars += chars

    def mark_tts_synthesis(self) -> None:
        if self._active:
            self._active.tts_synthesis_ms = self._elapsed()

    def mark_playback_start(self) -> None:
        if self._active:
            self._active.playback_start_ms = self._elapsed()

    def finish_turn(self, response_chars: int = 0, sentences: int = 0) -> Optional[VoiceTurnLatency]:
        if not self._active:
            return None
        self._active.total_ms = self._elapsed()
        self._active.response_chars = response_chars
        self._active.sentences = sentences
        rec = self._active
        self._history.appendleft(rec)
        self._active = None
        return rec

    # ── Query ───────────────────────────────────────────────────────────────

    def get_history(self, n: int = 10) -> list[dict]:
        return [asdict(t) for t in list(self._history)[:n]]

    def get_last(self) -> Optional[dict]:
        if self._history:
            return asdict(self._history[0])
        return None

    def summary_text(self, n: int = 5) -> str:
        """Human-readable summary for the 'show voice latency' command."""
        turns = list(self._history)[:n]
        if not turns:
            return "No voice turns recorded yet."
        lines = ["Voice pipeline latency (most recent first):"]
        lines.append(f"{'Turn':<12} {'STT':>7} {'1st tok':>8} {'1st sent':>9} {'TTS':>7} {'Playback':>9} {'Total':>7}")
        lines.append("-" * 66)
        for t in turns:
            lines.append(
                f"{t.turn_id[:11]:<12} "
                f"{t.stt_ms:>7.0f} "
                f"{t.llm_first_token_ms:>8.0f} "
                f"{t.first_sentence_ms:>9.0f} "
                f"{t.tts_synthesis_ms:>7.0f} "
                f"{t.playback_start_ms:>9.0f} "
                f"{t.total_ms:>7.0f}"
            )
        lines.append("")
        lines.append("All times in ms from query submission.")
        return "\n".join(lines)

    def _elapsed(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0


# ── Global singleton ───────────────────────────────────────────────────────────

_latency_logger = VoiceLatencyLogger()


def get_latency_logger() -> VoiceLatencyLogger:
    """Get the global voice latency logger."""
    return _latency_logger
