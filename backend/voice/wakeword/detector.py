"""
Wake word detector — diagnostics, cooldown bypass, and structured logging.

Cooldown behaviour:
  - Normal confidence (threshold ≤ prob < bypass): rejected during cooldown window.
  - High confidence (prob ≥ bypass_cooldown_confidence): bypasses cooldown immediately.
  - Cooldown log is emitted ONCE per cooldown window, not per chunk, to avoid log spam.
  - WAKE_WORD_COOLDOWN_SECONDS=0 disables cooldown entirely (default for debugging).

Log prefixes:
  [WAKE_STARTING]  — constructor called
  [WAKE_READY]     — model loaded OK
  [WAKE_DETECTED]  — probability exceeds threshold (not yet accepted)
  [WAKE_ACCEPTED]  — event sent to frontend; state change to LISTENING
  [WAKE_REJECTED]  — below threshold
  [WAKE_COOLDOWN]  — blocked by cooldown (logged once per cooldown window)
  [WAKE_ERROR]     — model load failure or runtime error
  [STATE_CHANGE]   — state machine transition
  [WAKE_AUDIO_LEVEL] — periodic mic RMS (debug level)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from backend.config import (
    WAKE_WORD_THRESHOLD,
    WAKE_WORD_COOLDOWN_SECONDS,
    WAKE_BYPASS_COOLDOWN_CONFIDENCE,
)

log = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).parent / "hey_silvia.onnx"


class WakeWordDetector:
    def __init__(
        self,
        model_path: str | Path = _MODEL_PATH,
        threshold: float | None = None,
        cooldown_seconds: float | None = None,
        bypass_cooldown_confidence: float | None = None,
    ) -> None:
        self._threshold = threshold if threshold is not None else WAKE_WORD_THRESHOLD
        self._cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else WAKE_WORD_COOLDOWN_SECONDS
        self._bypass_cooldown_confidence = (
            bypass_cooldown_confidence
            if bypass_cooldown_confidence is not None
            else WAKE_BYPASS_COOLDOWN_CONFIDENCE
        )

        self._last_trigger_time: float = 0.0
        self._cooldown_log_time: float = 0.0   # when we last logged [WAKE_COOLDOWN] for this window
        self._model_key = Path(model_path).stem
        self._last_error: str | None = None
        self._last_state_transition: str = "initialized"

        # Diagnostics counters
        self._last_confidence: float = 0.0
        self._last_raw_confidence: float = 0.0
        self._last_audio_level: float = 0.0
        self._total_triggers: int = 0
        self._rejected_below_threshold: int = 0
        self._rejected_cooldown: int = 0
        self._cooldown_bypassed: int = 0
        self._false_activations_today: int = 0
        self._day_key: str = ""
        self._chunks_processed: int = 0

        log.info(
            "[WAKE_STARTING] model=%s threshold=%.2f cooldown=%.1fs bypass_at=%.2f",
            self._model_key, self._threshold, self._cooldown_seconds, self._bypass_cooldown_confidence,
        )

        try:
            import openwakeword
            openwakeword.utils.download_models()
            self._oww = openwakeword.Model(
                wakeword_models=[str(model_path)],
                inference_framework="onnx",
            )
            log.info(
                "[WAKE_READY] model=%s threshold=%.2f cooldown=%.1fs bypass_at=%.2f",
                self._model_key, self._threshold, self._cooldown_seconds, self._bypass_cooldown_confidence,
            )
            self._last_state_transition = "ready"
        except Exception as exc:
            self._oww = None
            self._last_error = str(exc)
            self._last_state_transition = f"error: {exc}"
            log.error("[WAKE_ERROR] Failed to load wake word model: %s", exc)

    # ── Core detection ────────────────────────────────────────────────────────

    def process_chunk(self, audio_int16: np.ndarray) -> dict | None:
        """Process an audio chunk. Returns a wake event dict or None.

        Return dict fields:
          wake: True
          confidence: float (0-1)
          threshold: float
          accepted: bool
          rejected_reason: str | None
          bypassed_cooldown: bool
        """
        if self._oww is None:
            return None

        self._chunks_processed += 1

        # Track audio level (RMS)
        rms = float(np.sqrt(np.mean(audio_int16.astype(np.float32) ** 2))) / 32768.0
        self._last_audio_level = rms

        if self._chunks_processed % 80 == 0:
            log.debug("[WAKE_AUDIO_LEVEL] rms=%.4f chunks=%d", rms, self._chunks_processed)

        scores = self._oww.predict(audio_int16)
        prob = float(scores.get(self._model_key, 0.0))
        self._last_raw_confidence = prob

        if prob < 0.3:
            return None

        now = time.monotonic()
        self._last_confidence = prob

        today = time.strftime("%Y-%m-%d")
        if today != self._day_key:
            self._day_key = today
            self._false_activations_today = 0

        # Below threshold — always reject
        if prob < self._threshold:
            self._rejected_below_threshold += 1
            log.debug(
                "[WAKE_REJECTED] reason=below_threshold prob=%.3f threshold=%.2f",
                prob, self._threshold,
            )
            return {
                "wake": True,
                "confidence": prob,
                "threshold": self._threshold,
                "accepted": False,
                "rejected_reason": f"confidence {prob:.3f} < threshold {self._threshold:.2f}",
                "bypassed_cooldown": False,
            }

        # Cooldown check — with high-confidence bypass
        in_cooldown = (
            self._cooldown_seconds > 0
            and self._last_trigger_time > 0
            and (now - self._last_trigger_time) < self._cooldown_seconds
        )

        if in_cooldown:
            remaining = self._cooldown_seconds - (now - self._last_trigger_time)

            # High confidence → bypass cooldown immediately
            if prob >= self._bypass_cooldown_confidence:
                self._cooldown_bypassed += 1
                log.info(
                    "[WAKE_DETECTED] HIGH CONFIDENCE bypass_cooldown prob=%.3f bypass_threshold=%.2f remaining=%.1fs",
                    prob, self._bypass_cooldown_confidence, remaining,
                )
                return self._accept(now, prob, bypassed=True)

            # Normal confidence during cooldown — reject, but only log ONCE per cooldown window
            self._rejected_cooldown += 1
            if now - self._cooldown_log_time >= self._cooldown_seconds:
                self._cooldown_log_time = now
                log.info(
                    "[WAKE_COOLDOWN] prob=%.3f cooldown_remaining=%.1fs (suppressing further logs this window)",
                    prob, remaining,
                )
            return {
                "wake": True,
                "confidence": prob,
                "threshold": self._threshold,
                "accepted": False,
                "rejected_reason": f"cooldown ({remaining:.1f}s remaining)",
                "bypassed_cooldown": False,
            }

        # Accepted — above threshold, not in cooldown
        log.info("[WAKE_DETECTED] prob=%.3f threshold=%.2f", prob, self._threshold)
        return self._accept(now, prob, bypassed=False)

    def _accept(self, now: float, prob: float, *, bypassed: bool) -> dict:
        self._last_trigger_time = now
        self._total_triggers += 1
        self._last_state_transition = f"accepted conf={prob:.3f}"
        log.info(
            "[WAKE_ACCEPTED] confidence=%.3f bypassed_cooldown=%s total=%d",
            prob, bypassed, self._total_triggers,
        )
        log.info("[STATE_CHANGE] wake_listening -> listening")
        return {
            "wake": True,
            "confidence": prob,
            "threshold": self._threshold,
            "accepted": True,
            "rejected_reason": None,
            "bypassed_cooldown": bypassed,
        }

    # ── Control ───────────────────────────────────────────────────────────────

    def record_false_activation(self) -> None:
        self._false_activations_today += 1
        self._last_trigger_time = time.monotonic()
        self._last_state_transition = "false_activation"
        log.info("[WAKE_REJECTED] reason=false_activation")

    def reset_cooldown(self) -> None:
        """Clear any active cooldown — call when wake word seems stuck."""
        self._last_trigger_time = 0.0
        self._cooldown_log_time = 0.0
        self._last_state_transition = "cooldown_reset"
        log.info("[WAKE_COOLDOWN] Cooldown manually cleared.")

    def reset(self) -> None:
        if self._oww:
            self._oww.reset()
        self._last_trigger_time = 0.0

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def diagnostics(self) -> dict:
        now = time.monotonic()
        in_cooldown = (
            self._cooldown_seconds > 0
            and self._last_trigger_time > 0
            and (now - self._last_trigger_time) < self._cooldown_seconds
        )
        cooldown_remaining = (
            max(0.0, self._cooldown_seconds - (now - self._last_trigger_time))
            if self._last_trigger_time > 0 and self._cooldown_seconds > 0
            else 0.0
        )
        return {
            "model": self._model_key,
            "model_loaded": self._oww is not None,
            "threshold": self._threshold,
            "cooldown_seconds": self._cooldown_seconds,
            "bypass_cooldown_confidence": self._bypass_cooldown_confidence,
            "last_confidence": round(self._last_confidence, 4),
            "last_raw_confidence": round(self._last_raw_confidence, 4),
            "last_audio_level": round(self._last_audio_level, 5),
            "chunks_processed": self._chunks_processed,
            "total_accepted_triggers": self._total_triggers,
            "rejected_below_threshold": self._rejected_below_threshold,
            "rejected_cooldown": self._rejected_cooldown,
            "cooldown_bypassed": self._cooldown_bypassed,
            "false_activations_today": self._false_activations_today,
            "in_cooldown": in_cooldown,
            "cooldown_remaining_s": round(cooldown_remaining, 2),
            "last_state_transition": self._last_state_transition,
            "last_error": self._last_error,
        }


_singleton: WakeWordDetector | None = None


def get_detector() -> WakeWordDetector:
    global _singleton
    if _singleton is None:
        _singleton = WakeWordDetector()
    return _singleton
