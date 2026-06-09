"""
Silero VAD runner — ported directly from llm-voice-assistant's recordAudio().

Runs the same stateful ONNX model with EMA smoothing (alpha=0.3, threshold=0.3).
Model file: backend/voice/vad/silero_vad.onnx
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).parent / "silero_vad.onnx"
_FRAME_SIZE = 512    # 32ms at 16kHz (matches reference project: 0.032 * 16000)
_EMA_ALPHA = 0.3     # smoothing strength — same as reference project
_THRESHOLD = 0.3     # EMA confidence threshold — same as reference project

_session = None  # lazy, cached across calls


def _get_session():
    global _session
    if _session is None:
        try:
            import onnxruntime as ort
            _session = ort.InferenceSession(str(_MODEL_PATH))
            logger.info("Silero VAD model loaded from %s", _MODEL_PATH)
        except ImportError:
            logger.warning("onnxruntime not installed — Silero VAD unavailable (pip install onnxruntime)")
            return None
        except Exception as e:
            logger.warning("Failed to load Silero VAD model: %s", e)
            return None
    return _session


def run_vad(pcm_float32: np.ndarray, sample_rate: int = 16000) -> dict:
    """
    Run Silero VAD on a float32 PCM array decoded at `sample_rate` Hz.

    Algorithm is identical to llm-voice-assistant/main.py recordAudio():
    - Process 512-sample (32ms) frames
    - Stateful ONNX model, reset per call
    - EMA smoothing with alpha=0.3
    - Speech detected if EMA confidence ever reaches 0.3

    Returns dict with keys:
        speech_detected (bool | None)  — None if VAD unavailable
        max_ema_confidence (float)
        speech_ratio (float)           — fraction of frames above threshold
        vad_available (bool)
    """
    session = _get_session()
    if session is None:
        return {
            "speech_detected": None,
            "max_ema_confidence": None,
            "speech_ratio": None,
            "vad_available": False,
        }

    input_name = session.get_inputs()[0].name
    state_name = session.get_inputs()[1].name
    sr_name = session.get_inputs()[2].name

    # Fresh state for each call — stateful within a single audio clip
    state = np.zeros((2, 1, 128), dtype=np.float32)
    ema_confidence = 0.0
    max_ema_confidence = 0.0
    speech_frames = 0
    total_frames = 0

    offset = 0
    while offset + _FRAME_SIZE <= len(pcm_float32):
        frame = pcm_float32[offset : offset + _FRAME_SIZE]
        offset += _FRAME_SIZE
        total_frames += 1

        # Skip zero frames (same guard as reference project)
        if np.max(np.abs(frame)) == 0:
            continue

        inputs = {
            input_name: frame[np.newaxis, :].astype(np.float32),
            state_name: state,
            sr_name: np.array(sample_rate, dtype=np.int64),
        }

        outs = session.run(None, inputs)
        new_conf, state = outs  # [speech_prob, new_state]

        # new_conf may be shape (1,) or (1,1) — flatten to scalar
        conf_scalar = float(np.asarray(new_conf).flatten()[0])
        ema_confidence = _EMA_ALPHA * conf_scalar + (1.0 - _EMA_ALPHA) * ema_confidence
        max_ema_confidence = max(max_ema_confidence, ema_confidence)

        if ema_confidence >= _THRESHOLD:
            speech_frames += 1

    speech_ratio = speech_frames / total_frames if total_frames > 0 else 0.0
    speech_detected = max_ema_confidence >= _THRESHOLD

    logger.debug(
        "VAD: max_ema=%.3f, speech_ratio=%.2f, speech_detected=%s (%d frames)",
        max_ema_confidence, speech_ratio, speech_detected, total_frames,
    )

    return {
        "speech_detected": speech_detected,
        "max_ema_confidence": round(max_ema_confidence, 4),
        "speech_ratio": round(speech_ratio, 4),
        "vad_available": True,
    }
