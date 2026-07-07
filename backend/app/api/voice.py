import asyncio
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
    WAKE_BYPASS_COOLDOWN_CONFIDENCE,
    WAKE_CONFIRMATION_ENABLED,
    WAKE_MIN_COMMAND_WORDS,
    WAKE_WORD_COOLDOWN_SECONDS,
    WAKE_WORD_THRESHOLD,
    IGNORE_SYSTEM_AUDIO,
)
from backend.voice.wakeword.detector import get_detector

router = APIRouter(tags=["voice"])
logger = logging.getLogger(__name__)

# ── Test-wake injection ───────────────────────────────────────────────────────
# Active WebSocket connections register a queue here.
# POST /api/voice/test-wake puts an event into every queue → the WS loop sends it.
_inject_queues: set[asyncio.Queue] = set()

# ── TTS diagnostics (pushed from browser after each turn) ────────────────────
_tts_diag: dict = {}


@router.get("/voice/status", response_model=VoiceStatus)
async def voice_status(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> VoiceStatus:
    return platform_router.voice_service.status()


@router.get("/voice/diagnostics")
async def voice_diagnostics(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> dict:
    """Return detailed diagnostics for the voice pipeline — STT, TTS, wake word, config."""
    diag = platform_router.voice_service.diagnostics()
    try:
        detector = get_detector()
        diag["wake_word"] = detector.diagnostics()
    except Exception as exc:
        diag["wake_word"] = {"status": "not initialized", "error": str(exc)}
    diag["voice_mode"] = VOICE_MODE
    diag["wake_confirmation_enabled"] = WAKE_CONFIRMATION_ENABLED
    diag["wake_min_command_words"] = WAKE_MIN_COMMAND_WORDS
    diag["wake_bypass_cooldown_confidence"] = WAKE_BYPASS_COOLDOWN_CONFIDENCE
    diag["ignore_system_audio"] = IGNORE_SYSTEM_AUDIO
    diag["active_wake_websockets"] = len(_inject_queues)
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


@router.get("/voice/latency")
async def voice_latency(n: int = 10) -> dict:
    """Return the last N voice turn latency records.

    Use 'show voice latency' in the chat for a formatted table.
    """
    from backend.app.voice.pipeline_fast import get_latency_logger
    logger_inst = get_latency_logger()
    return {
        "turns": logger_inst.get_history(n),
        "last": logger_inst.get_last(),
        "summary": logger_inst.summary_text(n),
    }


@router.post("/voice/tts-diagnostics")
async def push_tts_diagnostics(body: dict) -> dict:
    """Browser pushes TTS diagnostics after each turn. Read with GET or 'show tts diagnostics'."""
    global _tts_diag
    _tts_diag = body
    return {"ok": True}


@router.get("/voice/tts-diagnostics")
async def get_tts_diagnostics() -> dict:
    """Return last TTS diagnostics pushed from the browser."""
    return _tts_diag or {"status": "no data yet — ask SILVIA a voice question first"}


@router.post("/voice/test-wake")
async def test_wake() -> dict:
    """Inject a simulated wake word event into all active WebSocket connections.

    Use this to test the voice pipeline without saying "Hey Silvia":
      curl -X POST http://localhost:8001/api/voice/test-wake

    Expected: frontend transitions to RECORDING state and accepts the next spoken command.
    """
    event = {
        "wake": True,
        "confidence": 1.0,
        "threshold": WAKE_WORD_THRESHOLD,
        "accepted": True,
        "rejected_reason": None,
        "test": True,
    }
    n = len(_inject_queues)
    for q in list(_inject_queues):
        await q.put(event)
    logger.info("[WAKE_DETECTED] test-wake injected to %d active connection(s)", n)
    return {"ok": True, "injected_to": n, "message": f"Wake event sent to {n} active WebSocket connection(s)."}


@router.post("/voice/wake/reset-cooldown")
async def reset_wake_cooldown() -> dict:
    """Clear any active wake word cooldown.

    Call this when the wake word seems stuck / unresponsive after a detection.
    """
    try:
        detector = get_detector()
        detector.reset_cooldown()
        return {"ok": True, "message": "Wake word cooldown cleared. Ready to detect again."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/voice/wake/false-activation")
async def report_false_activation() -> dict:
    """Frontend reports a false activation so cooldown is reset and stats tracked."""
    try:
        detector = get_detector()
        detector.record_false_activation()
        return {"ok": True, "message": "False activation recorded"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.websocket("/ws/wake")
async def wake_word_stream(websocket: WebSocket) -> None:
    """Stream audio chunks for wake word detection.

    Sends JSON events:
      {"wake": true, "confidence": 0.82, "accepted": true}   — wake detected
      {"wake": true, "confidence": 0.55, "accepted": false, "rejected_reason": "..."}

    Only accepted=true events trigger recording on the frontend.

    Also accepts injected events from POST /api/voice/test-wake.
    """
    await websocket.accept()
    detector = get_detector()
    logger.info(
        "[WAKE_READY] WebSocket connected — threshold=%.2f cooldown=%.1fs active_connections=%d",
        WAKE_WORD_THRESHOLD, WAKE_WORD_COOLDOWN_SECONDS, len(_inject_queues) + 1,
    )

    # Register this connection's inject queue
    inject_queue: asyncio.Queue = asyncio.Queue()
    _inject_queues.add(inject_queue)

    try:
        while True:
            # Race: wait for audio data OR an injected test-wake event
            audio_task = asyncio.ensure_future(websocket.receive_bytes())
            inject_task = asyncio.ensure_future(inject_queue.get())

            done, pending = await asyncio.wait(
                {audio_task, inject_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel the task that didn't win
            for t in pending:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

            if inject_task in done:
                # Injected event (test-wake) — send directly to frontend
                event = inject_task.result()
                logger.info("[WAKE_DETECTED] injected test event confidence=%.2f", event.get("confidence", 0))
                await websocket.send_json(event)
                continue

            # Real audio chunk from the frontend
            data = audio_task.result()
            audio = np.frombuffer(data, dtype=np.int16)
            event = detector.process_chunk(audio)
            if event is not None:
                if event["accepted"]:
                    bypassed = event.get("bypassed_cooldown", False)
                    logger.info(
                        "[WAKE_ACCEPTED] confidence=%.3f bypassed_cooldown=%s [STATE_CHANGE] wake_listening -> listening",
                        event["confidence"], bypassed,
                    )
                await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.info("[WAKE_ERROR] WebSocket disconnected")
    except Exception as exc:
        logger.warning("[WAKE_ERROR] WS error: %s", exc)
        try:
            await websocket.close(1011)
        except Exception:
            pass
    finally:
        _inject_queues.discard(inject_queue)
        logger.info(
            "Wake word WebSocket closed — remaining_connections=%d",
            len(_inject_queues),
        )
