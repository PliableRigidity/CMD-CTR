"""
Voice pipeline for the Personal AI Assistant.

Orchestrates speech-to-text and text-to-speech processing.

Current implementations:
- STT: OpenAI Whisper (local)
- TTS: pyttsx3 (local, Windows-compatible)
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class STTProvider(ABC):
    """Abstract base class for speech-to-text providers."""
    
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Convert audio bytes to text.
        
        Args:
            audio_bytes: Raw audio data
            
        Returns:
            Transcribed text
        """
        pass


class TTSProvider(ABC):
    """Abstract base class for text-to-speech providers."""
    
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Convert text to audio.
        
        Args:
            text: Text to synthesize
            
        Returns:
            Audio data bytes
        """
        pass


class VoicePipeline:
    """Orchestrates voice input/output."""
    
    def __init__(
        self,
        stt_provider: Optional[STTProvider] = None,
        tts_provider: Optional[TTSProvider] = None,
    ):
        """
        Initialize voice pipeline.
        
        Args:
            stt_provider: Speech-to-text provider
            tts_provider: Text-to-speech provider
        """
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider
        self.is_listening = False
    
    async def record_and_transcribe(self, audio_bytes: bytes) -> str:
        """
        Record audio and convert to text.
        
        Args:
            audio_bytes: Raw audio data
            
        Returns:
            Transcribed text
        """
        if not self.stt_provider:
            raise RuntimeError("STT provider not configured")
        
        logger.info("Starting speech-to-text...")
        text = await self.stt_provider.transcribe(audio_bytes)
        logger.info(f"Transcribed: {text}")
        return text
    
    async def synthesize_and_play(self, text: str) -> bytes:
        """
        Convert text to speech.
        
        Args:
            text: Text to speak
            
        Returns:
            Audio data
        """
        if not self.tts_provider:
            raise RuntimeError("TTS provider not configured")
        
        logger.info(f"Synthesizing: {text}")
        audio = await self.tts_provider.synthesize(text)
        logger.info(f"Synthesized {len(audio)} bytes of audio")
        return audio
    
    async def full_voice_interaction(
        self,
        audio_input: bytes,
        text_processor,  # Callable that takes text and returns response
    ) -> Tuple[str, bytes]:
        """
        Complete voice interaction: record → transcribe → process → synthesize.
        
        Args:
            audio_input: Input audio bytes
            text_processor: Function to process transcribed text
            
        Returns:
            Tuple of (response_text, response_audio)
        """
        # Transcribe
        user_text = await self.record_and_transcribe(audio_input)
        
        # Process through assistant
        response_text = await text_processor(user_text)
        
        # Synthesize response
        response_audio = await self.synthesize_and_play(response_text)
        
        return response_text, response_audio


# TODO: Implement concrete providers
# - WhisperSTT (in implementations/whisper_stt.py)
# - PyTTSXTTSProvider (in implementations/pyttsx3_tts.py)

# TODO: Add to Phase 2 implementation
# - RecordingManager (handle audio device selection)
# - AudioProcessor (audio format conversion, normalization)
# - VoiceActivityDetection (VAD for auto-stopping recording)
