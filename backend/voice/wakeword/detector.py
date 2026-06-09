"""
Wake word detector wrapping openwakeword's streaming predict() API.

Expects int16 PCM chunks at 16 kHz (any size; openwakeword buffers internally).
Returns True on the frame where the wake word probability crosses the threshold,
then enforces a cooldown to avoid repeated triggers on the same utterance.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).parent / "hey_silvia.onnx"
_THRESHOLD = 0.5
_COOLDOWN_FRAMES = 30   # ~2.4 s at 80ms/frame before re-triggering


class WakeWordDetector:
    def __init__(
        self,
        model_path: str | Path = _MODEL_PATH,
        threshold: float = _THRESHOLD,
    ) -> None:
        import openwakeword
        openwakeword.utils.download_models()   # no-op if already cached

        self._oww = openwakeword.Model(
            wakeword_models=[str(model_path)],
            inference_framework="onnx",
        )
        self._model_key = Path(model_path).stem
        self._threshold = threshold
        self._cooldown = 0
        log.info("WakeWordDetector ready — model=%s threshold=%.2f", self._model_key, threshold)

    def process_chunk(self, audio_int16: np.ndarray) -> bool:
        scores = self._oww.predict(audio_int16)
        prob = float(scores.get(self._model_key, 0.0))

        if self._cooldown > 0:
            self._cooldown -= 1
            return False

        if prob >= self._threshold:
            self._cooldown = _COOLDOWN_FRAMES
            log.info("Wake word detected — prob=%.3f", prob)
            return True

        return False

    def reset(self) -> None:
        self._oww.reset()
        self._cooldown = 0


# ---------------------------------------------------------------------------
# Module-level singleton — initialized once at startup to avoid per-connection
# load latency (openwakeword downloads + ONNX session creation takes ~5-90s).
# ---------------------------------------------------------------------------

_singleton: "WakeWordDetector | None" = None


def get_detector() -> "WakeWordDetector":
    global _singleton
    if _singleton is None:
        _singleton = WakeWordDetector()
    return _singleton
