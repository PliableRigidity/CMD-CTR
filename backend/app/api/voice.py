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
    return platform_router.voice_service.diagnostics()


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
        logger.error("Transcription failed: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Transcription error: %s", e, exc_info=True)
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
    logger.info("Synthesize request: %d chars", len(request.text))
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Empty text for synthesis")
    try:
        audio_bytes = await platform_router.voice_service.synthesize(request.text)
    except RuntimeError as e:
        logger.error("Synthesis failed: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Synthesis error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthesis error: {e}")
    await platform_router.event_service.emit(
        "Voice synthesis",
        f"Synthesized {len(request.text)} chars → {len(audio_bytes)} bytes audio.",
    )
    return Response(content=audio_bytes, media_type="audio/wav")


@router.websocket("/ws/wake")
async def wake_word_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    detector = get_detector()
    logger.info("Wake word WebSocket connected")
    try:
        while True:
            data = await websocket.receive_bytes()
            audio = np.frombuffer(data, dtype=np.int16)
            if detector.process_chunk(audio):
                await websocket.send_json({"wake": True})
    except WebSocketDisconnect:
        logger.info("Wake word WebSocket disconnected")
    except Exception as exc:
        logger.warning("Wake word WS error: %s", exc)
        try:
            await websocket.close(1011)
        except Exception:
            pass
