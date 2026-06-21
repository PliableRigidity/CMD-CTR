import logging

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from backend.app.api.deps import get_router
from backend.app.models.voice import (
    SynthesizeRequest,
    TranscribeResponse,
    VoiceStateUpdate,
    VoiceStatus,
)
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.config import (
    VOICE_MODE,
    WAKE_CONFIRMATION_ENABLED,
    WAKE_MIN_COMMAND_WORDS,
    WAKE_WORD_COOLDOWN_SECONDS,
    WAKE_WORD_THRESHOLD,
    IGNORE_SYSTEM_AUDIO,
)
from backend.voice.wakeword.detector import get_detector

router = APIRouter(tags=["voice"])
logger = logging.getLogger(__name__)


@router.get("/voice/status", response_model=VoiceStatus)
async def voice_status(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> VoiceStatus:
    return platform_router.voice_service.status()


@router.get("/voice/diagnostics")
async def voice_diagnostics(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> dict:
    """Return detailed diagnostics for the voice pipeline — STT, TTS, config."""
    diag = platform_router.voice_service.diagnostics()
    try:
        detector = get_detector()
        diag["wake_word"] = detector.diagnostics()
    except Exception:
        diag["wake_word"] = {"status": "not initialized"}
    diag["voice_mode"] = VOICE_MODE
    diag["wake_confirmation_enabled"] = WAKE_CONFIRMATION_ENABLED
    diag["wake_min_command_words"] = WAKE_MIN_COMMAND_WORDS
    diag["ignore_system_audio"] = IGNORE_SYSTEM_AUDIO
    return diag


@router.post("/voice/state", response_model=VoiceStatus)
async def update_voice_state(
    request: VoiceStateUpdate,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> VoiceStatus:
    status = platform_router.voice_service.update(request)
    await platform_router.event_service.emit(
        "Voice state",
        f"Listening={status.listening}, speaking={status.speaking}, speech_enabled={status.speech_enabled}.",
    )
    return status


@router.post("/voice/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> TranscribeResponse:
    audio_bytes = await audio.read()
    logger.info(
        "Transcribe request: filename=%s content_type=%s size=%d bytes",
        audio.filename,
        audio.content_type,
        len(audio_bytes),
    )
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file received")
    try:
        result = await platform_router.voice_service.transcribe(
            audio_bytes,
            mime_type=audio.content_type,
            filename=audio.filename,
        )
    except RuntimeError as e:
        logger.error("STT transcription failed: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("STT transcription error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")
    await platform_router.event_service.emit(
        "Voice transcription",
        result.message
        or f"Transcribed {len(result.text)} chars in {result.processing_time_ms:.0f}ms.",
    )
    return result


@router.post("/voice/synthesize")
async def synthesize_speech(
    request: SynthesizeRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> Response:
    logger.info("TTS synthesize request: %d chars", len(request.text))
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Empty text for synthesis")
    try:
        audio_bytes = await platform_router.voice_service.synthesize(request.text)
    except RuntimeError as e:
        logger.error("TTS synthesis failed: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("TTS synthesis error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthesis error: {e}")
    await platform_router.event_service.emit(
        "Voice synthesis",
        f"Synthesized {len(request.text)} chars -> {len(audio_bytes)} bytes audio.",
    )
    return Response(content=audio_bytes, media_type="audio/wav")


@router.post("/voice/wake/false-activation")
async def report_false_activation() -> dict:
    """Frontend reports a false activation so cooldown is reset and stats tracked."""
    try:
        detector = get_detector()
        detector.record_false_activation()
        return {"ok": True, "message": "False activation recorded, cooldown reset"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.websocket("/ws/wake")
async def wake_word_stream(websocket: WebSocket) -> None:
    """Stream audio chunks for wake word detection.

    Sends JSON events:
      {"wake": true, "confidence": 0.82, "accepted": true}   — wake detected, above threshold, not in cooldown
      {"wake": true, "confidence": 0.55, "accepted": false, "rejected_reason": "..."}  — below threshold or cooldown

    Only accepted=true events should trigger recording on the frontend.
    """
    await websocket.accept()
    detector = get_detector()
    logger.info("Wake word WebSocket connected (threshold=%.2f cooldown=%.1fs)",
                WAKE_WORD_THRESHOLD, WAKE_WORD_COOLDOWN_SECONDS)
    try:
        while True:
            data = await websocket.receive_bytes()
            audio = np.frombuffer(data, dtype=np.int16)
            event = detector.process_chunk(audio)
            if event is not None:
                if event["accepted"]:
                    logger.info(
                        "Wake word -> frontend: ACCEPTED confidence=%.3f",
                        event["confidence"],
                    )
                else:
                    logger.debug(
                        "Wake word -> frontend: REJECTED reason=%s confidence=%.3f",
                        event.get("rejected_reason", "?"), event["confidence"],
                    )
                await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("Wake word WebSocket disconnected")
    except Exception as exc:
        logger.warning("Wake word WS error: %s", exc)
        try:
            await websocket.close(1011)
        except Exception:
            pass
