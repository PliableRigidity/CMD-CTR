import httpx

from backend.config import OPEN_METEO_GEOCODE_URL


async def geocode_location(name: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(
            OPEN_METEO_GEOCODE_URL,
            params={"name": name, "count": 1, "language": "en", "format": "json"},
        )
        response.raise_for_status()
    results = response.json().get("results")
    if not results:
        raise ValueError(f"Could not geocode location: {name}")
    r = results[0]
    return {
        "name": r["name"],
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "country": r.get("country", ""),
        "country_code": r.get("country_code", ""),
        "timezone": r.get("timezone", ""),
    }
