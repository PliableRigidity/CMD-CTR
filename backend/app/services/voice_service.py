from backend.app.models.voice import VoiceStateUpdate, VoiceStatus


class VoiceService:
    def __init__(self) -> None:
        self._status = VoiceStatus(
            available=True,
            listening=False,
            speaking=False,
            stt_provider="browser-speech-recognition",
            tts_provider="browser-speech-synthesis",
            notes=[
                "Frontend browser voice capture is supported when the browser provides SpeechRecognition.",
                "Speech synthesis is handled in the browser for local playback.",
            ],
            speech_enabled=False,
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
