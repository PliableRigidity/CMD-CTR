from datetime import datetime, timezone

from backend.app.models.devices import DeviceStatus


class DeviceManager:
    def list_devices(self) -> list[DeviceStatus]:
        now = datetime.now(timezone.utc).isoformat()
        return [
            DeviceStatus(
                id="host-pc",
                name="Primary PC",
                type="desktop",
                status="online",
                location="Local workstation",
                heartbeat=now,
                capabilities=["conversation", "decision", "actions", "voice-output"],
            ),
            DeviceStatus(
                id="rpi-node-01",
                name="Raspberry Pi Node",
                type="edge",
                status="standby",
                location="Home lab",
                heartbeat=now,
                capabilities=["sensor-bridge", "future-automation"],
            ),
        ]
