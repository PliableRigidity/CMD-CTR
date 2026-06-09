from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from backend.app.models.voice import TranscribeResponse, VoiceStateUpdate, VoiceStatus
from backend.app.services.speech_sanitizer import sanitize_for_speech
from backend.config import (
    PIPER_CONFIG_PATH,
    PIPER_MODEL_PATH,
    PIPER_USE_CUDA,
    SPEACHES_API_KEY,
    SPEACHES_STT_MODEL,
    SPEACHES_TTS_MODEL,
    SPEACHES_TTS_VOICE,
    SPEACHES_URL,
    WHISPER_MODEL_SIZE,
)
from backend.voice.implementations.piper_tts import PiperTTS
from backend.voice.implementations.speaches_stt import SpeachesSTT
from backend.voice.implementations.speaches_tts import SpeachesTTS
from backend.voice.implementations.whisper_stt import WhisperSTT
from backend.voice.pipeline import VoicePipeline

logger = logging.getLogger(__name__)


# ── Local provider checks ─────────────────────────────────────────────────────

def _check_whisper_installed() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401
        return True, f"faster-whisper installed"
    except ImportError:
        return False, "faster-whisper not installed (run: pip install faster-whisper)"


def _check_piper_binary() -> tuple[bool, str]:
    binary = shutil.which("piper")
    if binary:
        return True, binary
    return False, "piper binary not found in PATH"


def _check_piper_model(model_path: str) -> tuple[bool, str]:
    if not model_path:
        return False, "PIPER_MODEL_PATH not set in .env"
    if Path(model_path).exists():
        return True, model_path
    return False, f"model file not found: {model_path}"


# ── Speaches availability check ───────────────────────────────────────────────

def _check_speaches(url: str) -> tuple[bool, str]:
    """Ping Speaches health endpoint to see if it's reachable."""
    if not url:
        return False, "SPEACHES_URL not configured"
    try:
        import urllib.request
        # Normalize URL — strip /v1 for health check
        base = url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        health_url = f"{base}/health"
        with urllib.request.urlopen(health_url, timeout=2) as r:
            if r.status == 200:
                return True, health_url
    except Exception as e:
        return False, f"Speaches unreachable at {url}: {e}"
    return False, f"Speaches health check failed at {url}"


class VoiceService:
    def __init__(self) -> None:
        # ── Determine which providers to use ─────────────────────────────────
        speaches_reachable, speaches_msg = _check_speaches(SPEACHES_URL)

        use_speaches_stt = speaches_reachable
        use_speaches_tts = speaches_reachable

        notes: list[str] = []

        if use_speaches_stt:
            stt = SpeachesSTT(
                base_url=SPEACHES_URL,
                api_key=SPEACHES_API_KEY,
                model=SPEACHES_STT_MODEL,
            )
            stt_label = f"Speaches ({SPEACHES_STT_MODEL.split('/')[-1]})"
            stt_ok = True
            notes.append(f"STT: {stt_label} @ {SPEACHES_URL}")
            logger.info("Voice: using Speaches STT — %s", SPEACHES_STT_MODEL)
        else:
            whisper_ok, whisper_msg = _check_whisper_installed()
            stt = WhisperSTT(model_size=WHISPER_MODEL_SIZE)
            stt_label = f"faster-whisper ({WHISPER_MODEL_SIZE})"
            stt_ok = whisper_ok
            if whisper_ok:
                notes.append(f"STT: {stt_label} (local)")
                if SPEACHES_URL:
                    notes.append(f"Speaches unavailable — {speaches_msg}")
            else:
                notes.append(f"STT unavailable — {whisper_msg}")
            logger.info("Voice: using local Whisper STT (%s) — Speaches: %s", WHISPER_MODEL_SIZE, speaches_msg)

        if use_speaches_tts:
            tts = SpeachesTTS(
                base_url=SPEACHES_URL,
                api_key=SPEACHES_API_KEY,
                model=SPEACHES_TTS_MODEL,
                voice=SPEACHES_TTS_VOICE,
            )
            tts_label = f"Speaches ({SPEACHES_TTS_MODEL.split('/')[-1]}, voice={SPEACHES_TTS_VOICE})"
            tts_ok = True
            notes.append(f"TTS: {tts_label}")
        else:
            piper_bin_ok, piper_bin_msg = _check_piper_binary()
            piper_model_ok, piper_model_msg = _check_piper_model(PIPER_MODEL_PATH)
            tts = PiperTTS(
                model_path=PIPER_MODEL_PATH,
                config_path=PIPER_CONFIG_PATH,
                use_cuda=PIPER_USE_CUDA,
            )
            tts_ok = piper_bin_ok and piper_model_ok
            if tts_ok:
                notes.append(f"TTS: Piper local — {Path(PIPER_MODEL_PATH).name}")
            elif not piper_bin_ok:
                notes.append(f"TTS unavailable — {piper_bin_msg}")
            else:
                notes.append(f"TTS unavailable — {piper_model_msg}")
            tts_label = f"piper ({Path(PIPER_MODEL_PATH).name})"

        self._pipeline = VoicePipeline(stt_provider=stt, tts_provider=tts)

        self._status = VoiceStatus(
            available=stt_ok or tts_ok,
            stt_available=stt_ok,
            tts_available=tts_ok,
            listening=False,
            speaking=False,
            stt_provider=stt_label,
            tts_provider=tts_label,
            notes=notes,
            speech_enabled=False,
        )

        logger.info(
            "VoiceService ready: STT=%s(%s) TTS=%s(%s)",
            "speaches" if use_speaches_stt else "local",
            stt_ok,
            "speaches" if use_speaches_tts else "local",
            tts_ok,
        )

    def status(self) -> VoiceStatus:
        return self._status

    def update(self, request: VoiceStateUpdate) -> VoiceStatus:
        data = self._status.model_dump()
        if request.listening is not None:
            data["listening"] = request.listening
        if request.speaking is not None:
            data["speaking"] = request.speaking
        if request.speech_enabled is not None:
            data["speech_enabled"] = request.speech_enabled
        self._status = VoiceStatus(**data)
        return self._status

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> TranscribeResponse:
        if not self._status.stt_available:
            note = next((n for n in self._status.notes if "STT" in n), "STT unavailable")
            raise RuntimeError(note)
        started = time.perf_counter()
        self.update(VoiceStateUpdate(listening=True))
        try:
            provider = self._pipeline.stt_provider
            if hasattr(provider, "transcribe_with_diagnostics"):
                result = await provider.transcribe_with_diagnostics(
                    audio_bytes,
                    mime_type=mime_type,
                    filename=filename,
                )
            else:
                text = await self._pipeline.record_and_transcribe(audio_bytes)
                result = {"text": text, "message": None, "diagnostics": None}
        finally:
            self.update(VoiceStateUpdate(listening=False))
        elapsed = (time.perf_counter() - started) * 1000
        text = (result.get("text") or "").strip()
        logger.info("Transcription complete: %d chars in %.0fms", len(text), elapsed)
        return TranscribeResponse(
            text=text,
            processing_time_ms=elapsed,
            message=result.get("message"),
            diagnostics=result.get("diagnostics"),
        )

    async def synthesize(self, text: str) -> bytes:
        if not self._status.tts_available:
            note = next((n for n in self._status.notes if "TTS" in n), "TTS unavailable")
            raise RuntimeError(note)
        spoken_text = sanitize_for_speech(text)
        if not spoken_text:
            raise RuntimeError("No speakable text produced for synthesis")
        self.update(VoiceStateUpdate(speaking=True))
        try:
            audio_bytes = await self._pipeline.synthesize_and_play(spoken_text)
        finally:
            self.update(VoiceStateUpdate(speaking=False))
        return audio_bytes

    def diagnostics(self) -> dict:
        speaches_reachable, speaches_msg = _check_speaches(SPEACHES_URL)
        whisper_ok, whisper_msg = _check_whisper_installed()
        piper_bin_ok, piper_bin_msg = _check_piper_binary()
        piper_model_ok, piper_model_msg = _check_piper_model(PIPER_MODEL_PATH)

        return {
            "speaches": {
                "url": SPEACHES_URL or "(not configured)",
                "reachable": speaches_reachable,
                "status": "ready" if speaches_reachable else "unavailable",
                "detail": speaches_msg,
                "stt_model": SPEACHES_STT_MODEL,
                "tts_model": SPEACHES_TTS_MODEL,
                "tts_voice": SPEACHES_TTS_VOICE,
            },
            "stt": {
                "active_provider": "speaches" if speaches_reachable else "local-whisper",
                "provider": "faster-whisper (local)",
                "model_size": WHISPER_MODEL_SIZE,
                "installed": whisper_ok,
                "status": "ready" if whisper_ok else "unavailable",
                "detail": whisper_msg,
            },
            "tts": {
                "active_provider": "speaches" if speaches_reachable else "local-piper",
                "provider": "piper (local)",
                "binary_found": piper_bin_ok,
                "binary_path": piper_bin_msg if piper_bin_ok else None,
                "model_path": PIPER_MODEL_PATH,
                "model_exists": piper_model_ok,
                "status": "ready" if (piper_bin_ok and piper_model_ok) else "unavailable",
                "detail": piper_model_msg if not piper_model_ok else (piper_bin_msg if not piper_bin_ok else "ok"),
            },
            "config": {
                "whisper_model_size": WHISPER_MODEL_SIZE,
                "piper_model_path": PIPER_MODEL_PATH,
                "speaches_url": SPEACHES_URL or "(disabled)",
                "speaches_stt_model": SPEACHES_STT_MODEL,
                "speaches_tts_model": SPEACHES_TTS_MODEL,
                "speaches_tts_voice": SPEACHES_TTS_VOICE,
            },
        }
