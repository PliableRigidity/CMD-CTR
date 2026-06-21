"""
Speaches STT provider — calls the Speaches OpenAI-compatible transcription API.

Mirrors exactly how llm-voice-assistant calls:
    client.audio.transcriptions.create(model=..., response_format="verbose_json", file=...)

Speaches is a local server that wraps faster-whisper behind an OpenAI-compatible REST API.
Configure SPEACHES_URL in .env (e.g. http://localhost:9000/v1).
"""

import asyncio
import io
import logging
import time

from backend.voice.pipeline import STTProvider

logger = logging.getLogger(__name__)

_MIME_EXT = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp4": "mp4",
}


def _mime_to_ext(mime_type: str | None) -> str:
    base = (mime_type or "").split(";")[0].strip().lower()
    return _MIME_EXT.get(base, "webm")


class SpeachesSTT(STTProvider):
    def __init__(self, base_url: str, api_key: str = "speaches", model: str = "Systran/faster-whisper-small") -> None:
        raw = base_url.rstrip("/")
        if raw.endswith("/v1"):
            self._base_url = raw[:-3]
        else:
            self._base_url = raw
        self._api_key = api_key
        self._model = model
        self._client = None

    @property
    def available(self) -> bool:
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def error(self) -> str | None:
        return None

    def _client_instance(self):
        if self._client is None:
            from openai import OpenAI
            api_base = f"{self._base_url}/v1"
            logger.info("SpeachesSTT: OpenAI client base_url=%s", api_base)
            self._client = OpenAI(base_url=api_base, api_key=self._api_key)
        return self._client

    async def transcribe(self, audio_bytes: bytes) -> str:
        result = await self.transcribe_with_diagnostics(audio_bytes)
        return result["text"]

    async def transcribe_with_diagnostics(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(self._transcribe_sync, audio_bytes, mime_type, filename)

    def _transcribe_sync(
        self,
        audio_bytes: bytes,
        mime_type: str | None,
        filename: str | None,
    ) -> dict:
        if not audio_bytes:
            raise ValueError("Empty audio data")

        ext = _mime_to_ext(mime_type)
        fname = filename or f"recording.{ext}"

        # Wrap bytes in a file-like object with a .name attribute — same as reference project's
        # `with Path(audioInput).open("rb") as audio_file: client.audio.transcriptions.create(..., file=audio_file)`
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = fname

        client = self._client_instance()
        started = time.perf_counter()

        logger.info(
            "Speaches STT: %d bytes (%s) -> model=%s @ %s",
            len(audio_bytes), ext, self._model, self._base_url,
        )

        try:
            result = client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
                response_format="verbose_json",
            )
        except Exception as e:
            err = str(e)
            if "404" in err or "Not Found" in err:
                logger.error(
                    "Speaches STT: 404 Not Found at %s/v1/audio/transcriptions — "
                    "SPEACHES_BASE_URL may be pointing at the wrong server (e.g. CMD-CTR backend instead of Speaches)",
                    self._base_url,
                )
                raise RuntimeError(
                    f"STT endpoint not found at {self._base_url}. "
                    f"Check SPEACHES_BASE_URL — it may be pointing at the CMD-CTR backend instead of the Speaches service."
                ) from e
            if "Connection" in err or "refused" in err.lower():
                logger.error("Speaches STT: connection refused at %s", self._base_url)
                raise RuntimeError(
                    f"STT provider not reachable at {self._base_url}. Check SPEACHES_BASE_URL."
                ) from e
            logger.error("Speaches STT failed: %s", e)
            raise RuntimeError(f"Speaches STT error: {e}") from e

        elapsed_ms = (time.perf_counter() - started) * 1000
        text = (result.text or "").strip()
        language = getattr(result, "language", None)

        logger.info(
            "Speaches STT: got %d chars in %.0fms (lang=%s)",
            len(text), elapsed_ms, language,
        )

        return {
            "text": text,
            "message": None if text else "No speech detected",
            "diagnostics": {
                "provider": "speaches",
                "model": self._model,
                "audio_size_bytes": len(audio_bytes),
                "detected_extension": ext,
                "language": language,
                "language_probability": getattr(result, "language_probability", None),
                "speech_detected": bool(text),
                "raw_transcript": text,
                "final_transcript": text,
                "transcription_confidence": None,
                "fallback_used": False,
            },
        }
