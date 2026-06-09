from pydantic import BaseModel


class VoiceStatus(BaseModel):
    available: bool
    stt_available: bool = False
    tts_available: bool = False
    listening: bool
    speaking: bool
    stt_provider: str
    tts_provider: str
    notes: list[str]
    speech_enabled: bool = False


class VoiceStateUpdate(BaseModel):
    listening: bool | None = None
    speaking: bool | None = None
    speech_enabled: bool | None = None


class TranscribeResponse(BaseModel):
    text: str
    processing_time_ms: float
    message: str | None = None
    diagnostics: dict | None = None


class SynthesizeRequest(BaseModel):
    text: str
