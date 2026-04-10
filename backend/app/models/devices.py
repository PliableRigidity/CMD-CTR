from pydantic import BaseModel


class DeviceStatus(BaseModel):
    id: str
    name: str
    type: str
    status: str
    location: str
    heartbeat: str
    capabilities: list[str]
