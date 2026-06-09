from datetime import datetime, timezone

import httpx

from backend.app.tools.geo import geocode_location
from backend.config import OPENWEATHER_API_KEY, OPENWEATHER_BASE_URL


async def get_weather(location_name: str) -> dict:
    if not OPENWEATHER_API_KEY:
        raise RuntimeError("OPENWEATHER_API_KEY is not configured — set it in .env")
    location = await geocode_location(location_name)
    lat, lon = location["latitude"], location["longitude"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            OPENWEATHER_BASE_URL,
            params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"},
        )
        response.raise_for_status()
    data = response.json()
    weather = (data.get("weather") or [{}])[0]
    main = data.get("main", {})
    wind = data.get("wind", {})
    desc = (weather.get("description") or weather.get("main") or "").lower()
    temp_c = main.get("temp")
    wind_ms = wind.get("speed")
    wind_kmh = round(wind_ms * 3.6, 1) if wind_ms is not None else None
    dt_unix = data.get("dt")
    time_iso = datetime.fromtimestamp(dt_unix, tz=timezone.utc).isoformat() if dt_unix else None
    place = f'{location["name"]}, {location.get("country", "")}'.strip(", ")
    return {
        "place": place,
        "temperature_c": temp_c,
        "wind_speed_kmh": wind_kmh,
        "weather_desc": desc,
        "time": time_iso,
    }
