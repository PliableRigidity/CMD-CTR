import asyncio
import logging
import os
import subprocess
import tempfile
from math import exp

import numpy as np
from backend.voice.pipeline import STTProvider
from backend.voice.vad.silero_vad_runner import run_vad

logger = logging.getLogger(__name__)

# Map common audio MIME prefixes to file extensions that ffmpeg/soundfile recognize
_MIME_EXT = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
}

_WAV_MAGIC = b"RIFF"
_WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
_OGG_MAGIC = b"OggS"
_MP3_MAGIC = (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"ID3")


def _detect_extension(audio_bytes: bytes) -> str:
    """Detect audio format from magic bytes and return the correct file extension."""
    if audio_bytes[:4] == _WAV_MAGIC:
        return ".wav"
    if audio_bytes[:4] == _WEBM_MAGIC:
        return ".webm"
    if audio_bytes[:4] == _OGG_MAGIC:
        return ".ogg"
    if any(audio_bytes[:3] == m or audio_bytes[:3] == m[:3] for m in _MP3_MAGIC):
        return ".mp3"
    # Fallback: no extension lets ffmpeg auto-detect from content
    logger.warning("Unknown audio format — ffmpeg will auto-detect")
    return ".bin"


class WhisperSTT(STTProvider):
    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None
        self._available: bool | None = None
        self._error: str | None = None

    @property
    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def error(self) -> str | None:
        return self._error

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise RuntimeError(
                    "faster-whisper is not installed. Run: pip install faster-whisper"
                ) from e
            logger.info("Loading faster-whisper model: %s (first use — this may take a moment)", self._model_size)
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            logger.info("faster-whisper model loaded: %s", self._model_size)
        return self._model

    async def transcribe(self, audio_bytes: bytes) -> str:
        logger.debug("WhisperSTT.transcribe: received %d bytes", len(audio_bytes))
        return await asyncio.to_thread(self._transcribe_sync, audio_bytes)

    async def transcribe_with_diagnostics(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> dict:
        logger.debug("WhisperSTT.transcribe_with_diagnostics: received %d bytes", len(audio_bytes))
        return await asyncio.to_thread(
            self._transcribe_with_diagnostics_sync,
            audio_bytes,
            mime_type,
            filename,
        )

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        result = self._transcribe_with_diagnostics_sync(audio_bytes, None, None)
        return result["text"]

    def _transcribe_with_diagnostics_sync(
        self,
        audio_bytes: bytes,
        mime_type: str | None,
        filename: str | None,
    ) -> dict:
        if not audio_bytes:
            raise ValueError("Empty audio data received")

        ext = _detect_extension(audio_bytes)
        logger.info("STT: audio format detected as '%s' (%d bytes)", ext, len(audio_bytes))

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name

        try:
            analysis = self._analyze_audio_file(tmp)
            diagnostics = {
                "filename": filename,
                "mime_type": mime_type,
                "audio_size_bytes": len(audio_bytes),
                "detected_extension": ext,
                **analysis,
            }

            if not diagnostics["speech_detected"]:
                diagnostics.update(
                    {
                        "raw_transcript": "",
                        "final_transcript": "",
                        "language": None,
                        "language_probability": None,
                        "transcription_confidence": None,
                        "avg_logprob": None,
                        "no_speech_probability": 1.0,
                        "fallback_used": True,
                    }
                )
                return {
                    "text": "",
                    "message": "No speech detected",
                    "diagnostics": diagnostics,
                }

            model = self._load()
            logger.info("STT: transcribing %s with beam_size=5 vad_filter=true", tmp)
            segments, info = model.transcribe(
                tmp,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
                condition_on_previous_text=False,
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
            )
            segments = list(segments)
            raw_text = " ".join(seg.text for seg in segments).strip()
            avg_logprob = self._average(
                getattr(seg, "avg_logprob", None) for seg in segments
            )
            no_speech_probability = self._average(
                getattr(seg, "no_speech_prob", None) for seg in segments
            )
            confidence = None if avg_logprob is None else round(float(exp(min(0.0, avg_logprob))), 4)
            final_text, message, fallback_used = self._finalize_transcript(
                raw_text=raw_text,
                speech_detected=diagnostics["speech_detected"],
                duration_seconds=diagnostics["duration_seconds"],
                no_speech_probability=no_speech_probability,
                confidence=confidence,
            )
            diagnostics.update(
                {
                    "raw_transcript": raw_text,
                    "final_transcript": final_text,
                    "language": getattr(info, "language", None),
                    "language_probability": getattr(info, "language_probability", None),
                    "transcription_confidence": confidence,
                    "avg_logprob": avg_logprob,
                    "no_speech_probability": no_speech_probability,
                    "fallback_used": fallback_used,
                }
            )
            logger.info(
                "STT: transcribed %d chars in language=%s (prob=%.2f)",
                len(final_text),
                getattr(info, "language", None),
                getattr(info, "language_probability", 0.0) or 0.0,
            )
            return {
                "text": final_text,
                "message": message,
                "diagnostics": diagnostics,
            }
        except Exception as e:
            logger.error("STT: transcription error: %s", e, exc_info=True)
            raise
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _analyze_audio_file(self, source_path: str) -> dict:
        """
        Decode audio to 16kHz float32 PCM via ffmpeg, then run Silero VAD.
        Falls back to amplitude-only check when onnxruntime is unavailable.
        """
        try:
            completed = subprocess.run(
                [
                    "ffmpeg", "-v", "error",
                    "-i", source_path,
                    "-ac", "1", "-ar", "16000",
                    "-f", "f32le", "pipe:1",
                ],
                check=True,
                capture_output=True,
            )
            samples = np.frombuffer(completed.stdout, dtype=np.float32)
            sample_rate = 16000
            duration_seconds = round(float(len(samples) / sample_rate), 3) if len(samples) else 0.0
            peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
            rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
            rms_db = round(20 * np.log10(max(rms, 1e-8)), 2)
            peak_db = round(20 * np.log10(max(peak, 1e-8)), 2)

            # Primary: Silero VAD (same model + algorithm as llm-voice-assistant)
            vad_result = run_vad(samples, sample_rate=sample_rate)

            if vad_result["vad_available"]:
                # Trust Silero VAD, with minimum duration guard
                speech_detected = bool(
                    vad_result["speech_detected"]
                    and duration_seconds >= 0.6
                )
                logger.debug(
                    "STT: Silero VAD max_ema=%.3f → speech_detected=%s",
                    vad_result["max_ema_confidence"] or 0.0, speech_detected,
                )
            else:
                # Fallback: amplitude check (requires onnxruntime install)
                speech_detected = bool(
                    duration_seconds >= 0.6
                    and rms_db > -42.0
                    and peak > 0.02
                )

            return {
                "duration_seconds": duration_seconds,
                "sample_rate_hz": sample_rate,
                "rms_db": rms_db,
                "peak_db": peak_db,
                "speech_detected": speech_detected,
                "vad_max_ema": vad_result.get("max_ema_confidence"),
                "vad_speech_ratio": vad_result.get("speech_ratio"),
            }
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "STT: ffmpeg analysis failed: %s",
                exc.stderr.decode(errors="ignore") if exc.stderr else exc,
            )
            return {
                "duration_seconds": 0.0,
                "sample_rate_hz": 16000,
                "rms_db": -120.0,
                "peak_db": -120.0,
                "speech_detected": False,
                "vad_max_ema": None,
                "vad_speech_ratio": None,
            }

    def _finalize_transcript(
        self,
        *,
        raw_text: str,
        speech_detected: bool,
        duration_seconds: float,
        no_speech_probability: float | None,
        confidence: float | None,
    ) -> tuple[str, str | None, bool]:
        cleaned = raw_text.strip()
        if not cleaned:
            return "", "No speech detected", True

        # Expanded list of common Whisper hallucinations on short/noisy audio
        short_hallucinations = {
            "yes", "yeah", "yep", "uh", "hmm", "hm", "mm", "huh", "ok", "okay",
            "no", "hi", "hey", "bye", "ah", "oh", "uh-huh", "mhm", "thanks",
            "thank you", "you", "the", "a", "i",
        }
        # Words in the hallucination set require very strong evidence to pass:
        # duration > 2.5s, high confidence, and low no-speech probability
        is_likely_hallucination = cleaned.lower() in short_hallucinations
        if is_likely_hallucination and (
            not speech_detected
            or duration_seconds < 2.5
            or (no_speech_probability is not None and no_speech_probability >= 0.4)
            or (confidence is not None and confidence < 0.5)
        ):
            logger.info(
                "STT: filtered likely hallucination %r (dur=%.2fs, conf=%s, no_speech=%s)",
                cleaned, duration_seconds, confidence, no_speech_probability,
            )
            return "", "No speech detected", True

        return cleaned, None, False

    @staticmethod
    def _average(values) -> float | None:
        numbers = [float(value) for value in values if value is not None]
        if not numbers:
            return None
        return round(sum(numbers) / len(numbers), 4)
