import zoneinfo
from datetime import datetime

from backend.app.tools.geo import geocode_location
from backend.config import TIMEZONE

# Lazy-load timezonefinder once at module level
try:
    from timezonefinder import TimezoneFinder as _TZF
    _TZ_FINDER = _TZF()
except ImportError:
    _TZ_FINDER = None

# Alias map — checked before any geocoding.
# Prevents geocoders from returning wrong country-level matches
# (e.g. "England" → England, Arkansas, USA).
_ALIAS: dict[str, str] = {
    # United Kingdom
    "uk": "Europe/London",
    "united kingdom": "Europe/London",
    "england": "Europe/London",
    "scotland": "Europe/London",
    "wales": "Europe/London",
    "northern ireland": "Europe/London",
    "great britain": "Europe/London",
    "britain": "Europe/London",
    "london": "Europe/London",
    "bristol": "Europe/London",
    "manchester": "Europe/London",
    "birmingham": "Europe/London",
    "liverpool": "Europe/London",
    "edinburgh": "Europe/London",
    "glasgow": "Europe/London",
    "cardiff": "Europe/London",
    "belfast": "Europe/London",
    "leeds": "Europe/London",
    "sheffield": "Europe/London",
    "oxford": "Europe/London",
    "cambridge": "Europe/London",
    # Singapore
    "singapore": "Asia/Singapore",
    # United States
    "new york": "America/New_York",
    "new york city": "America/New_York",
    "nyc": "America/New_York",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "washington": "America/New_York",
    "washington dc": "America/New_York",
    "dc": "America/New_York",
    "atlanta": "America/New_York",
    "philadelphia": "America/New_York",
    "chicago": "America/Chicago",
    "houston": "America/Chicago",
    "dallas": "America/Chicago",
    "austin": "America/Chicago",
    "denver": "America/Denver",
    "phoenix": "America/Phoenix",
    "seattle": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "sf": "America/Los_Angeles",
    "las vegas": "America/Los_Angeles",
    "portland": "America/Los_Angeles",
    "honolulu": "Pacific/Honolulu",
    "hawaii": "Pacific/Honolulu",
    "alaska": "America/Anchorage",
    "anchorage": "America/Anchorage",
    # Canada
    "toronto": "America/Toronto",
    "canada": "America/Toronto",
    "montreal": "America/Toronto",
    "ottawa": "America/Toronto",
    "vancouver": "America/Vancouver",
    "calgary": "America/Edmonton",
    "edmonton": "America/Edmonton",
    # Europe
    "paris": "Europe/Paris",
    "france": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "munich": "Europe/Berlin",
    "frankfurt": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam",
    "netherlands": "Europe/Amsterdam",
    "madrid": "Europe/Madrid",
    "spain": "Europe/Madrid",
    "barcelona": "Europe/Madrid",
    "rome": "Europe/Rome",
    "italy": "Europe/Rome",
    "milan": "Europe/Rome",
    "stockholm": "Europe/Stockholm",
    "sweden": "Europe/Stockholm",
    "oslo": "Europe/Oslo",
    "norway": "Europe/Oslo",
    "helsinki": "Europe/Helsinki",
    "finland": "Europe/Helsinki",
    "copenhagen": "Europe/Copenhagen",
    "denmark": "Europe/Copenhagen",
    "brussels": "Europe/Brussels",
    "belgium": "Europe/Brussels",
    "zurich": "Europe/Zurich",
    "switzerland": "Europe/Zurich",
    "geneva": "Europe/Zurich",
    "vienna": "Europe/Vienna",
    "austria": "Europe/Vienna",
    "warsaw": "Europe/Warsaw",
    "poland": "Europe/Warsaw",
    "prague": "Europe/Prague",
    "czech republic": "Europe/Prague",
    "budapest": "Europe/Budapest",
    "hungary": "Europe/Budapest",
    "bucharest": "Europe/Bucharest",
    "romania": "Europe/Bucharest",
    "sofia": "Europe/Sofia",
    "bulgaria": "Europe/Sofia",
    "athens": "Europe/Athens",
    "greece": "Europe/Athens",
    "lisbon": "Europe/Lisbon",
    "portugal": "Europe/Lisbon",
    "dublin": "Europe/Dublin",
    "ireland": "Europe/Dublin",
    "reykjavik": "Atlantic/Reykjavik",
    "iceland": "Atlantic/Reykjavik",
    "moscow": "Europe/Moscow",
    "russia": "Europe/Moscow",
    "st petersburg": "Europe/Moscow",
    "kyiv": "Europe/Kiev",
    "ukraine": "Europe/Kiev",
    "istanbul": "Europe/Istanbul",
    "turkey": "Europe/Istanbul",
    # Middle East
    "dubai": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "united arab emirates": "Asia/Dubai",
    "abu dhabi": "Asia/Dubai",
    "riyadh": "Asia/Riyadh",
    "saudi arabia": "Asia/Riyadh",
    "tel aviv": "Asia/Jerusalem",
    "jerusalem": "Asia/Jerusalem",
    "israel": "Asia/Jerusalem",
    "tehran": "Asia/Tehran",
    "iran": "Asia/Tehran",
    "baghdad": "Asia/Baghdad",
    "iraq": "Asia/Baghdad",
    "beirut": "Asia/Beirut",
    "lebanon": "Asia/Beirut",
    "amman": "Asia/Amman",
    "jordan": "Asia/Amman",
    # Asia
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "osaka": "Asia/Tokyo",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "seoul": "Asia/Seoul",
    "south korea": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "taipei": "Asia/Taipei",
    "taiwan": "Asia/Taipei",
    "bangkok": "Asia/Bangkok",
    "thailand": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta",
    "indonesia": "Asia/Jakarta",
    "kuala lumpur": "Asia/Kuala_Lumpur",
    "malaysia": "Asia/Kuala_Lumpur",
    "manila": "Asia/Manila",
    "philippines": "Asia/Manila",
    "delhi": "Asia/Kolkata",
    "new delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "karachi": "Asia/Karachi",
    "pakistan": "Asia/Karachi",
    "dhaka": "Asia/Dhaka",
    "bangladesh": "Asia/Dhaka",
    "colombo": "Asia/Colombo",
    "sri lanka": "Asia/Colombo",
    "kathmandu": "Asia/Kathmandu",
    "nepal": "Asia/Kathmandu",
    "kabul": "Asia/Kabul",
    "afghanistan": "Asia/Kabul",
    # Oceania
    "sydney": "Australia/Sydney",
    "australia": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth",
    "auckland": "Pacific/Auckland",
    "new zealand": "Pacific/Auckland",
    "wellington": "Pacific/Auckland",
    # Latin America
    "mexico city": "America/Mexico_City",
    "mexico": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
    "brazil": "America/Sao_Paulo",
    "rio": "America/Sao_Paulo",
    "rio de janeiro": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "argentina": "America/Argentina/Buenos_Aires",
    "santiago": "America/Santiago",
    "chile": "America/Santiago",
    "lima": "America/Lima",
    "peru": "America/Lima",
    "bogota": "America/Bogota",
    "colombia": "America/Bogota",
    # Africa
    "cairo": "Africa/Cairo",
    "egypt": "Africa/Cairo",
    "nairobi": "Africa/Nairobi",
    "kenya": "Africa/Nairobi",
    "johannesburg": "Africa/Johannesburg",
    "south africa": "Africa/Johannesburg",
    "cape town": "Africa/Johannesburg",
    "lagos": "Africa/Lagos",
    "nigeria": "Africa/Lagos",
    "accra": "Africa/Accra",
    "ghana": "Africa/Accra",
    "casablanca": "Africa/Casablanca",
    "morocco": "Africa/Casablanca",
    "addis ababa": "Africa/Addis_Ababa",
    "ethiopia": "Africa/Addis_Ababa",
}


def get_time() -> dict:
    tz = zoneinfo.ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    return {
        "ok": True,
        "iso": now.isoformat(timespec="seconds"),
        "current_time": now.isoformat(timespec="seconds"),
        "tz": TIMEZONE,
        "timezone": TIMEZONE,
        "human": now.strftime("%I:%M %p").lstrip("0"),
        "place": None,
        "source": "local",
    }


async def get_time_in(location_name: str) -> dict:
    key = location_name.lower().strip()

    # 1. Alias map — deterministic, zero network cost.
    # Also check just the city portion of "city, country" queries.
    city_part = key.split(",")[0].strip()
    alias_key = key if key in _ALIAS else (city_part if city_part in _ALIAS else None)
    if alias_key is not None:
        tz_name = _ALIAS[alias_key]
        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.now(tz)
        return {
            "ok": True,
            "place": location_name.title(),
            "timezone": tz_name,
            "tz": tz_name,
            "iso": now.isoformat(timespec="seconds"),
            "current_time": now.isoformat(timespec="seconds"),
            "human": now.strftime("%I:%M %p").lstrip("0"),
            "source": "alias_map",
        }

    # 2. Geocode → timezonefinder (lat/lng → accurate IANA timezone)
    try:
        location = await geocode_location(location_name)
    except ValueError:
        raise ValueError(
            f"Unable to find location: {location_name!r}. "
            "Try a city name (e.g. 'Bristol') or country (e.g. 'France')."
        )

    lat = location["latitude"]
    lng = location["longitude"]

    tz_name: str = ""
    source = "geocoder"

    if _TZ_FINDER is not None:
        tz_name = _TZ_FINDER.timezone_at(lng=lng, lat=lat) or ""
        if tz_name:
            source = "geocoder+timezonefinder"

    # Fall back to geocoder's own timezone field if timezonefinder missed
    if not tz_name:
        tz_name = location.get("timezone", "")

    if not tz_name:
        raise ValueError(
            f"Unable to determine timezone for {location['name']}, {location['country']}."
        )

    tz = zoneinfo.ZoneInfo(tz_name)
    now = datetime.now(tz)
    place = f"{location['name']}, {location['country']}".strip(", ")

    return {
        "ok": True,
        "place": place,
        "timezone": tz_name,
        "tz": tz_name,
        "iso": now.isoformat(timespec="seconds"),
        "current_time": now.isoformat(timespec="seconds"),
        "human": now.strftime("%I:%M %p").lstrip("0"),
        "source": source,
    }
