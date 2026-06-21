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
    SPEACHES_BASE_URL,
    SPEACHES_STT_MODEL,
    SPEACHES_TRANSCRIBE_ENDPOINT,
    SPEACHES_TTS_MODEL,
    SPEACHES_TTS_VOICE,
    STT_PROVIDER,
    TTS_PROVIDER,
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
    """Verify Speaches is actually running at the given URL.

    Guards against false positives: if the URL points at the CMD-CTR backend
    (which also has /health), the transcription endpoint won't exist and
    every STT call would 404.
    """
    if not url:
        return False, "SPEACHES_BASE_URL not configured"

    import urllib.request
    import json

    base = url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]

    # 1. Check if the transcription endpoint exists (OPTIONS or a model list)
    #    This distinguishes Speaches from any other server that has /health.
    try:
        models_url = f"{base}/v1/models"
        with urllib.request.urlopen(models_url, timeout=3) as r:
            if r.status == 200:
                body = json.loads(r.read())
                models = body.get("data", body.get("models", []))
                if isinstance(models, list) and len(models) > 0:
                    return True, f"Speaches OK at {base} ({len(models)} models)"
                return True, f"Speaches reachable at {base} (no models listed)"
    except Exception:
        pass

    # 2. Fall back to /health but verify the response looks like Speaches
    try:
        health_url = f"{base}/health"
        with urllib.request.urlopen(health_url, timeout=2) as r:
            if r.status == 200:
                body = r.read().decode("utf-8", errors="replace").lower()
                if "silvia" in body or '"service"' in body:
                    return False, (
                        f"SPEACHES_BASE_URL ({base}) points at the CMD-CTR backend, not Speaches. "
                        f"Speaches and CMD-CTR must run on different ports."
                    )
                return True, f"Speaches health OK at {base}"
    except Exception as e:
        return False, f"Speaches not reachable at {base}: {e}"

    return False, f"Speaches health check failed at {base}"


class VoiceService:
    def __init__(self) -> None:
        speaches_reachable, speaches_msg = _check_speaches(SPEACHES_BASE_URL)
        self._last_stt_error: str | None = None

        notes: list[str] = []

        # ── STT provider selection ───────────────────────────────────────────
        use_speaches_stt = STT_PROVIDER == "speaches" and speaches_reachable

        if use_speaches_stt:
            stt = SpeachesSTT(
                base_url=SPEACHES_BASE_URL,
                api_key=SPEACHES_API_KEY,
                model=SPEACHES_STT_MODEL,
            )
            stt_label = f"Speaches ({SPEACHES_STT_MODEL.split('/')[-1]})"
            stt_ok = True
            notes.append(f"STT: {stt_label} @ {SPEACHES_BASE_URL}")
            logger.info("Voice STT: Speaches — model=%s url=%s", SPEACHES_STT_MODEL, SPEACHES_BASE_URL)
        else:
            whisper_ok, whisper_msg = _check_whisper_installed()
            stt = WhisperSTT(model_size=WHISPER_MODEL_SIZE)
            stt_label = f"faster-whisper ({WHISPER_MODEL_SIZE})"
            stt_ok = whisper_ok
            if STT_PROVIDER == "speaches" and not speaches_reachable:
                notes.append(f"STT: Speaches requested but unavailable — {speaches_msg}")
                if whisper_ok:
                    notes.append(f"STT: Falling back to local {stt_label}")
                    logger.warning("Voice STT: Speaches unavailable (%s), falling back to local Whisper", speaches_msg)
                else:
                    notes.append(f"STT: Fallback also unavailable — {whisper_msg}")
                    logger.error("Voice STT: Speaches unavailable AND local Whisper unavailable")
            elif whisper_ok:
                notes.append(f"STT: {stt_label} (local)")
                logger.info("Voice STT: local faster-whisper (%s)", WHISPER_MODEL_SIZE)
            else:
                notes.append(f"STT: Not configured — {whisper_msg}")
                logger.warning("Voice STT: Not configured — %s", whisper_msg)

        # ── TTS provider selection ───────────────────────────────────────────
        use_speaches_tts = TTS_PROVIDER == "speaches" and speaches_reachable

        if use_speaches_tts:
            tts = SpeachesTTS(
                base_url=SPEACHES_BASE_URL,
                api_key=SPEACHES_API_KEY,
                model=SPEACHES_TTS_MODEL,
                voice=SPEACHES_TTS_VOICE,
            )
            tts_label = f"Speaches ({SPEACHES_TTS_MODEL.split('/')[-1]}, voice={SPEACHES_TTS_VOICE})"
            tts_ok = True
            notes.append(f"TTS: {tts_label}")
            logger.info("Voice TTS: Speaches — model=%s voice=%s", SPEACHES_TTS_MODEL, SPEACHES_TTS_VOICE)
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
                logger.info("Voice TTS: local Piper — %s", Path(PIPER_MODEL_PATH).name)
            elif not piper_bin_ok:
                notes.append(f"TTS: Not configured — {piper_bin_msg}")
                logger.warning("Voice TTS: Not configured — %s", piper_bin_msg)
            else:
                notes.append(f"TTS: Not configured — {piper_model_msg}")
                logger.warning("Voice TTS: Not configured — %s", piper_model_msg)
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
            "Voice startup health: STT=%s TTS=%s",
            "OK" if stt_ok else "Failed/Not configured",
            "OK" if tts_ok else "Failed/Not configured",
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
            self._last_stt_error = None
        except Exception as e:
            err_msg = str(e)
            self._last_stt_error = err_msg
            if "404" in err_msg or "Not Found" in err_msg:
                raise RuntimeError(
                    f"STT transcription endpoint not found. "
                    f"Check SPEACHES_BASE_URL ({SPEACHES_BASE_URL or 'not set'}) — "
                    f"it may be pointing at the wrong server or port."
                ) from e
            if "Connection" in err_msg or "unreachable" in err_msg.lower():
                raise RuntimeError(
                    f"STT provider not reachable. "
                    f"Check SPEACHES_BASE_URL ({SPEACHES_BASE_URL or 'not set'})."
                ) from e
            raise
        finally:
            self.update(VoiceStateUpdate(listening=False))
        elapsed = (time.perf_counter() - started) * 1000
        text = (result.get("text") or "").strip()
        logger.info("STT transcription complete: %d chars in %.0fms", len(text), elapsed)
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
        speaches_reachable, speaches_msg = _check_speaches(SPEACHES_BASE_URL)
        whisper_ok, whisper_msg = _check_whisper_installed()
        piper_bin_ok, piper_bin_msg = _check_piper_binary()
        piper_model_ok, piper_model_msg = _check_piper_model(PIPER_MODEL_PATH)

        # Check if transcription endpoint actually exists
        transcribe_ok = False
        transcribe_detail = "not checked"
        if speaches_reachable and SPEACHES_BASE_URL:
            try:
                import urllib.request
                base = SPEACHES_BASE_URL.rstrip("/")
                if base.endswith("/v1"):
                    base = base[:-3]
                url = f"{base}{SPEACHES_TRANSCRIBE_ENDPOINT}"
                req = urllib.request.Request(url, method="OPTIONS")
                with urllib.request.urlopen(req, timeout=3) as r:
                    transcribe_ok = r.status < 500
                    transcribe_detail = f"endpoint reachable ({r.status})"
            except Exception as e:
                transcribe_detail = f"endpoint check failed: {e}"

        return {
            "speaches": {
                "base_url": SPEACHES_BASE_URL or "(not configured)",
                "transcribe_endpoint": SPEACHES_TRANSCRIBE_ENDPOINT,
                "reachable": speaches_reachable,
                "server_status": speaches_msg,
                "transcribe_endpoint_ok": transcribe_ok,
                "transcribe_detail": transcribe_detail,
                "stt_model": SPEACHES_STT_MODEL,
                "tts_model": SPEACHES_TTS_MODEL,
                "tts_voice": SPEACHES_TTS_VOICE,
            },
            "stt": {
                "configured_provider": STT_PROVIDER,
                "active_provider": self._status.stt_provider,
                "available": self._status.stt_available,
                "last_error": self._last_stt_error,
                "local_whisper_installed": whisper_ok,
                "local_whisper_detail": whisper_msg,
                "local_whisper_model": WHISPER_MODEL_SIZE,
            },
            "tts": {
                "configured_provider": TTS_PROVIDER,
                "active_provider": self._status.tts_provider,
                "available": self._status.tts_available,
                "local_piper_binary": piper_bin_ok,
                "local_piper_binary_path": piper_bin_msg if piper_bin_ok else None,
                "local_piper_model_path": PIPER_MODEL_PATH,
                "local_piper_model_exists": piper_model_ok,
                "local_piper_detail": piper_model_msg if not piper_model_ok else (piper_bin_msg if not piper_bin_ok else "ok"),
            },
            "config": {
                "STT_PROVIDER": STT_PROVIDER,
                "TTS_PROVIDER": TTS_PROVIDER,
                "SPEACHES_BASE_URL": SPEACHES_BASE_URL or "(not set)",
                "SPEACHES_TRANSCRIBE_ENDPOINT": SPEACHES_TRANSCRIBE_ENDPOINT,
                "SPEACHES_STT_MODEL": SPEACHES_STT_MODEL,
                "SPEACHES_TTS_MODEL": SPEACHES_TTS_MODEL,
                "SPEACHES_TTS_VOICE": SPEACHES_TTS_VOICE,
                "WHISPER_MODEL_SIZE": WHISPER_MODEL_SIZE,
                "PIPER_MODEL_PATH": PIPER_MODEL_PATH,
            },
        }
