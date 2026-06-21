"""
Wake word detector with hardening against false activations.

Features:
  - Configurable confidence threshold (WAKE_WORD_THRESHOLD, default 0.75)
  - Time-based cooldown after every trigger (WAKE_WORD_COOLDOWN_SECONDS)
  - Confirmation mode: wake returns confidence so the caller can require
    a follow-up command before acting
  - Diagnostics: tracks false activations, last confidence, rejection reasons
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from backend.config import WAKE_WORD_THRESHOLD, WAKE_WORD_COOLDOWN_SECONDS

log = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).parent / "hey_silvia.onnx"


class WakeWordDetector:
    def __init__(
        self,
        model_path: str | Path = _MODEL_PATH,
        threshold: float | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        import openwakeword
        openwakeword.utils.download_models()

        self._oww = openwakeword.Model(
            wakeword_models=[str(model_path)],
            inference_framework="onnx",
        )
        self._model_key = Path(model_path).stem
        self._threshold = threshold if threshold is not None else WAKE_WORD_THRESHOLD
        self._cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else WAKE_WORD_COOLDOWN_SECONDS
        self._last_trigger_time: float = 0.0

        self._last_confidence: float = 0.0
        self._last_raw_confidence: float = 0.0
        self._total_triggers: int = 0
        self._rejected_below_threshold: int = 0
        self._rejected_cooldown: int = 0
        self._false_activations_today: int = 0
        self._day_key: str = ""

        log.info(
            "WakeWordDetector ready — model=%s threshold=%.2f cooldown=%.1fs",
            self._model_key, self._threshold, self._cooldown_seconds,
        )

    def process_chunk(self, audio_int16: np.ndarray) -> dict | None:
        """Process an audio chunk. Returns a wake event dict or None.

        The dict contains:
          wake: True
          confidence: float (0-1)
          threshold: float
          accepted: bool (whether confidence >= threshold AND not in cooldown)
          rejected_reason: str | None
        """
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

        if prob < self._threshold:
            self._rejected_below_threshold += 1
            log.debug(
                "Wake word below threshold — prob=%.3f threshold=%.2f (rejected)",
                prob, self._threshold,
            )
            return {
                "wake": True,
                "confidence": prob,
                "threshold": self._threshold,
                "accepted": False,
                "rejected_reason": f"confidence {prob:.3f} < threshold {self._threshold:.2f}",
            }

        elapsed = now - self._last_trigger_time
        if elapsed < self._cooldown_seconds:
            self._rejected_cooldown += 1
            remaining = self._cooldown_seconds - elapsed
            log.info(
                "Wake word in cooldown — prob=%.3f cooldown_remaining=%.1fs (rejected)",
                prob, remaining,
            )
            return {
                "wake": True,
                "confidence": prob,
                "threshold": self._threshold,
                "accepted": False,
                "rejected_reason": f"cooldown ({remaining:.1f}s remaining)",
            }

        self._last_trigger_time = now
        self._total_triggers += 1
        log.info("Wake word ACCEPTED — prob=%.3f threshold=%.2f", prob, self._threshold)
        return {
            "wake": True,
            "confidence": prob,
            "threshold": self._threshold,
            "accepted": True,
            "rejected_reason": None,
        }

    def record_false_activation(self) -> None:
        self._false_activations_today += 1
        self._last_trigger_time = time.monotonic()
        log.info("Wake word marked as false activation (cooldown reset)")

    def reset(self) -> None:
        self._oww.reset()
        self._last_trigger_time = 0.0

    def diagnostics(self) -> dict:
        return {
            "threshold": self._threshold,
            "cooldown_seconds": self._cooldown_seconds,
            "last_confidence": round(self._last_confidence, 4),
            "last_raw_confidence": round(self._last_raw_confidence, 4),
            "total_accepted_triggers": self._total_triggers,
            "rejected_below_threshold": self._rejected_below_threshold,
            "rejected_cooldown": self._rejected_cooldown,
            "false_activations_today": self._false_activations_today,
            "in_cooldown": (time.monotonic() - self._last_trigger_time) < self._cooldown_seconds if self._last_trigger_time else False,
            "cooldown_remaining": max(0, self._cooldown_seconds - (time.monotonic() - self._last_trigger_time)) if self._last_trigger_time else 0,
        }


_singleton: WakeWordDetector | None = None


def get_detector() -> WakeWordDetector:
    global _singleton
    if _singleton is None:
        _singleton = WakeWordDetector()
    return _singleton
