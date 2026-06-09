"""
Speaches TTS provider — calls the Speaches OpenAI-compatible speech API.

Mirrors exactly how llm-voice-assistant's textToSpeech.py calls:
    openai.audio.speech.create(model=..., voice=..., input=..., response_format="wav")

Speaches supports Piper TTS and Kokoro TTS models behind an OpenAI-compatible API.
Default model: Kokoro (pre-installed in Speaches), falls back to Piper if configured.

Configure in .env:
    SPEACHES_URL=http://localhost:9000/v1
    SPEACHES_TTS_MODEL=speaches-ai/Kokoro-82M-v1.0-ONNX
    SPEACHES_TTS_VOICE=af_aoede
"""

import asyncio
import logging
import time

from backend.voice.pipeline import TTSProvider

logger = logging.getLogger(__name__)


class SpeachesTTS(TTSProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str = "speaches",
        model: str = "speaches-ai/Kokoro-82M-v1.0-ONNX",
        voice: str = "af_aoede",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._voice = voice
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
            url = self._base_url
            if not url.endswith("/v1"):
                url = url + "/v1"
            self._client = OpenAI(base_url=url, api_key=self._api_key)
        return self._client

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        client = self._client_instance()
        started = time.perf_counter()

        logger.info(
            "Speaches TTS: %d chars → model=%s voice=%s",
            len(text), self._model, self._voice,
        )

        try:
            response = client.audio.speech.create(
                model=self._model,
                voice=self._voice,
                input=text,
                response_format="wav",
            )
            # response.response.read() — same pattern as reference project
            audio_bytes = response.response.read()
        except Exception as e:
            logger.error("Speaches TTS failed: %s", e)
            raise RuntimeError(f"Speaches TTS error: {e}") from e

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("Speaches TTS: %d bytes in %.0fms", len(audio_bytes), elapsed_ms)
        return audio_bytes
