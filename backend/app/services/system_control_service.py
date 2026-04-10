from __future__ import annotations

import ctypes
from ctypes import POINTER, cast

from backend.app.models.system import AudioState, MediaActionResponse

try:
    from pycaw.pycaw import AudioUtilities
except Exception:  # pragma: no cover
    AudioUtilities = None


VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
KEYEVENTF_KEYUP = 0x0002


class SystemControlService:
    def __init__(self) -> None:
        self.backend = "keyboard_fallback"
        self._endpoint = None
        try:
            if AudioUtilities is None:
                raise RuntimeError("pycaw is unavailable")
            devices = AudioUtilities.GetSpeakers()
            if hasattr(devices, "EndpointVolume"):
                self._endpoint = devices.EndpointVolume
            else:
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume

                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._endpoint = cast(interface, POINTER(IAudioEndpointVolume))
            self.backend = "pycaw"
        except Exception:
            self._endpoint = None

    def get_audio_state(self) -> AudioState:
        if self._endpoint is None:
            return AudioState(available=True, volume_percent=None, muted=None, backend=self.backend)
        scalar = float(self._endpoint.GetMasterVolumeLevelScalar())
        muted = bool(self._endpoint.GetMute())
        return AudioState(
            available=True,
            volume_percent=int(round(scalar * 100)),
            muted=muted,
            backend=self.backend,
        )

    def set_volume(self, volume_percent: int) -> AudioState:
        if self._endpoint is None:
            return self.get_audio_state()
        scalar = max(0.0, min(1.0, volume_percent / 100))
        self._endpoint.SetMasterVolumeLevelScalar(scalar, None)
        return self.get_audio_state()

    def volume_up(self) -> AudioState:
        if self._endpoint is not None:
            current = self.get_audio_state().volume_percent or 0
            return self.set_volume(min(100, current + 5))
        self._tap_key(VK_VOLUME_UP)
        return self.get_audio_state()

    def volume_down(self) -> AudioState:
        if self._endpoint is not None:
            current = self.get_audio_state().volume_percent or 0
            return self.set_volume(max(0, current - 5))
        self._tap_key(VK_VOLUME_DOWN)
        return self.get_audio_state()

    def toggle_mute(self) -> AudioState:
        if self._endpoint is not None:
            muted = bool(self._endpoint.GetMute())
            self._endpoint.SetMute(0 if muted else 1, None)
            return self.get_audio_state()
        self._tap_key(VK_VOLUME_MUTE)
        return self.get_audio_state()

    def media_play_pause(self) -> MediaActionResponse:
        self._tap_key(VK_MEDIA_PLAY_PAUSE)
        return MediaActionResponse(success=True, action="play_pause", message="Toggled media play/pause.")

    def media_next(self) -> MediaActionResponse:
        self._tap_key(VK_MEDIA_NEXT_TRACK)
        return MediaActionResponse(success=True, action="next_track", message="Skipped to next track.")

    def media_previous(self) -> MediaActionResponse:
        self._tap_key(VK_MEDIA_PREV_TRACK)
        return MediaActionResponse(success=True, action="previous_track", message="Moved to previous track.")

    def _tap_key(self, vk_code: int) -> None:
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
