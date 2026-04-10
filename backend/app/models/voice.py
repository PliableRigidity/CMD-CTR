from pydantic import BaseModel


class VoiceStatus(BaseModel):
    available: bool
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
