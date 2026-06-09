import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.voice.pipeline import TTSProvider

logger = logging.getLogger(__name__)


def _piper_binary() -> str | None:
    """Return the piper binary path, or None if not found."""
    return shutil.which("piper")


def _check_piper(model_path: str) -> tuple[bool, str]:
    """Return (available, reason) for the Piper TTS setup."""
    binary = _piper_binary()
    if not binary:
        return False, "piper binary not found in PATH"
    if not model_path:
        return False, "PIPER_MODEL_PATH not configured"
    if not Path(model_path).exists():
        return False, f"Piper model not found: {model_path}"
    return True, "ok"


class PiperTTS(TTSProvider):
    def __init__(self, model_path: str, config_path: str = "", use_cuda: bool = False) -> None:
        self.model_path = model_path
        self.config_path = config_path
        self.use_cuda = use_cuda
        self._available, self._error = _check_piper(model_path)
        if self._available:
            logger.info("PiperTTS ready — model: %s", model_path)
        else:
            logger.warning("PiperTTS unavailable: %s", self._error)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error if not self._available else None

    async def synthesize(self, text: str) -> bytes:
        logger.debug("PiperTTS.synthesize: %d chars", len(text))
        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        if not self._available:
            raise RuntimeError(f"Piper TTS unavailable: {self._error}")

        binary = _piper_binary()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name

        try:
            cmd = [binary, "--model", self.model_path, "--output_file", output_path]
            if self.config_path:
                cmd.extend(["--config", self.config_path])
            if self.use_cuda:
                cmd.append("--cuda")

            logger.info("TTS: piper cmd: %s", " ".join(cmd))
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _, stderr = process.communicate(input=text.encode("utf-8"))

            if process.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error("TTS: piper exited with code %d: %s", process.returncode, err_msg)
                raise RuntimeError(f"Piper TTS failed (exit {process.returncode}): {err_msg}")

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Piper produced no audio output. stderr: {err_msg}")

            audio_size = os.path.getsize(output_path)
            logger.info("TTS: synthesized %d bytes of WAV audio", audio_size)

            with open(output_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
