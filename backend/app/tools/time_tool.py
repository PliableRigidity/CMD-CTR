import zoneinfo
from datetime import datetime

from backend.app.tools.geo import geocode_location
from backend.config import TIMEZONE


def get_time() -> dict:
    tz = zoneinfo.ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    return {
        "iso": now.isoformat(timespec="seconds"),
        "tz": TIMEZONE,
        "human": now.strftime("%I:%M %p").lstrip("0"),
        "place": None,
    }


async def get_time_in(location_name: str) -> dict:
    location = await geocode_location(location_name)
    tz_name = location.get("timezone", "")
    if not tz_name:
        raise ValueError(f"No timezone found for: {location_name}")
    tz = zoneinfo.ZoneInfo(tz_name)
    now = datetime.now(tz)
    place = f'{location["name"]}, {location["country"]}'.strip(", ")
    return {
        "place": place,
        "tz": tz_name,
        "iso": now.isoformat(timespec="seconds"),
        "human": now.strftime("%I:%M %p").lstrip("0"),
    }
