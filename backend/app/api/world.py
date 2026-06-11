import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, Query

import httpx

from backend.app.api.deps import get_router
from backend.app.models.world import WorldEvent
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.app.world.rss_ingestor import rss_ingestor
from backend.config import OPENWEATHER_API_KEY


router = APIRouter(tags=["world"])

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# ── Simple TTL caches to avoid hammering external APIs ─────────────────────
_USGS_CACHE:    dict = {"data": None, "ts": 0.0}
_WEATHER_CACHE: dict = {"data": None, "ts": 0.0}
_MARKETS_CACHE: dict = {"data": None, "ts": 0.0}
_USGS_TTL    = 300   # 5 min — USGS updates ~every few minutes
_WEATHER_TTL = 600   # 10 min — weather changes slowly
_MARKETS_TTL = 60    # 1 min — market prices

# ── Cities matching mockEngine.js for weather ──────────────────────────────
_WEATHER_CITIES = [
    {"id": "1",  "name": "London",       "lat": 51.5,  "lng": -0.1  },
    {"id": "2",  "name": "New York",     "lat": 40.7,  "lng": -74.0 },
    {"id": "3",  "name": "Tokyo",        "lat": 35.6,  "lng": 139.6 },
    {"id": "4",  "name": "Moscow",       "lat": 55.7,  "lng": 37.6  },
    {"id": "5",  "name": "Beijing",      "lat": 39.9,  "lng": 116.4 },
    {"id": "6",  "name": "Mumbai",       "lat": 19.0,  "lng": 72.8  },
    {"id": "7",  "name": "Sao Paulo",    "lat": -23.5, "lng": -46.6 },
    {"id": "8",  "name": "Cairo",        "lat": 30.0,  "lng": 31.2  },
    {"id": "9",  "name": "Sydney",       "lat": -33.8, "lng": 151.2 },
    {"id": "10", "name": "Singapore",    "lat": 1.3,   "lng": 103.8 },
    {"id": "11", "name": "Dubai",        "lat": 25.2,  "lng": 55.2  },
    {"id": "12", "name": "Berlin",       "lat": 52.5,  "lng": 13.4  },
    {"id": "13", "name": "Paris",        "lat": 48.8,  "lng": 2.3   },
    {"id": "14", "name": "Lagos",        "lat": 6.5,   "lng": 3.3   },
    {"id": "15", "name": "Seoul",        "lat": 37.5,  "lng": 127.0 },
    {"id": "16", "name": "Istanbul",     "lat": 41.0,  "lng": 29.0  },
    {"id": "17", "name": "Mexico City",  "lat": 19.4,  "lng": -99.1 },
    {"id": "18", "name": "Johannesburg", "lat": -26.2, "lng": 28.0  },
    {"id": "19", "name": "Buenos Aires", "lat": -34.6, "lng": -58.4 },
]

# display_key → yahoo_symbol
_MARKET_TICKERS = [
    ("LMT", "LMT"),
    ("RTX", "RTX"),
    ("NOC", "NOC"),
    ("CL",  "CL=F"),   # WTI Crude Oil futures
    ("BZ",  "BZ=F"),   # Brent Crude futures
]


@router.get("/world/events", response_model=list[WorldEvent])
async def list_world_events(
    live: bool = Query(default=True),
    category: str | None = Query(default=None),
    country: str | None = Query(default=None),
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> list[WorldEvent]:
    if live:
        events = await rss_ingestor.ingest()
    else:
        events = platform_router.world_events_service.list_events()
        
    if category and category != "all" and category != "":
        events = [event for event in events if event.category == category]
    
    if country and country != "All regions" and country != "":
        if country == "Global":
            events = [event for event in events if event.is_global]
        else:
            events = [event for event in events if event.primary_country == country or event.country == country]
            
    return events


@router.get("/world/stock/{symbol}")
async def get_stock_quote(symbol: str) -> dict:
    """Proxy to Yahoo Finance — returns price, change, sparkline for one symbol."""
    sym = symbol.upper().strip()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=5m&range=1d"
    try:
        async with httpx.AsyncClient(headers=_YF_HEADERS, timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=f"Yahoo Finance error for {sym}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Yahoo Finance: {exc}")

    data = resp.json()
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        error_msg = data.get("chart", {}).get("error", {})
        raise HTTPException(status_code=404, detail=f"Symbol not found: {sym} — {error_msg}")

    meta = result.get("meta", {})
    closes_raw = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    sparkline = [round(c, 4) for c in closes_raw if c is not None]

    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or 0
    price = meta.get("regularMarketPrice") or (sparkline[-1] if sparkline else 0)
    change = price - prev_close if prev_close else 0
    change_pct = (change / prev_close * 100) if prev_close else 0

    return {
        "symbol": meta.get("symbol", sym),
        "name": meta.get("shortName") or meta.get("longName") or sym,
        "price": round(price, 2),
        "change": round(change, 2),
        "changePercent": round(change_pct, 2),
        "high": meta.get("regularMarketDayHigh"),
        "low": meta.get("regularMarketDayLow"),
        "volume": meta.get("regularMarketVolume"),
        "currency": meta.get("currency", "USD"),
        "marketState": meta.get("marketState", "CLOSED"),
        "sparkline": sparkline[-48:],  # last ~4h of 5-min bars
    }


@router.get("/world/earthquakes")
async def get_earthquakes() -> list[dict]:
    """Live earthquakes from USGS (past 24 h, mag ≥ 2.0)."""
    now = time.time()
    if _USGS_CACHE["data"] and now - _USGS_CACHE["ts"] < _USGS_TTL:
        return _USGS_CACHE["data"]

    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"USGS unreachable: {exc}")

    features = resp.json().get("features", [])
    results = []
    for i, f in enumerate(features):
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        mag = props.get("mag") or 0
        if mag < 2.0:
            continue
        lon, lat = coords[0], coords[1]
        if lat is None or lon is None:
            continue
        ts_ms = props.get("time") or 0
        results.append({
            "id":    f.get("id", f"eq_{i}"),
            "lat":   round(lat, 4),
            "lng":   round(lon, 4),
            "mag":   round(mag, 1),
            "title": props.get("place") or f"M{mag:.1f} earthquake",
            "time":  str(ts_ms),
        })
        if len(results) >= 60:
            break

    _USGS_CACHE["data"] = results
    _USGS_CACHE["ts"]   = now
    return results


async def _fetch_city_weather(client: httpx.AsyncClient, city: dict) -> dict | None:
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={city['lat']}&lon={city['lng']}&appid={OPENWEATHER_API_KEY}&units=metric"
    )
    try:
        resp = await client.get(url, timeout=8.0)
        resp.raise_for_status()
        d = resp.json()
        return {
            "id":          city["id"],
            "name":        city["name"],
            "lat":         city["lat"],
            "lng":         city["lng"],
            "temp":        round(d["main"]["temp"], 1),
            "condition":   d["weather"][0]["main"],
            "description": d["weather"][0]["description"],
            "wind":        round(d["wind"]["speed"], 1),
        }
    except Exception:
        return None


@router.get("/world/weather")
async def get_weather() -> list[dict]:
    """Live weather for 19 major cities from OpenWeatherMap."""
    if not OPENWEATHER_API_KEY:
        raise HTTPException(status_code=503, detail="OPENWEATHER_API_KEY not configured")

    now = time.time()
    if _WEATHER_CACHE["data"] and now - _WEATHER_CACHE["ts"] < _WEATHER_TTL:
        return _WEATHER_CACHE["data"]

    async with httpx.AsyncClient() as client:
        tasks = [_fetch_city_weather(client, city) for city in _WEATHER_CITIES]
        results_raw = await asyncio.gather(*tasks)

    results = [r for r in results_raw if r is not None]
    _WEATHER_CACHE["data"] = results
    _WEATHER_CACHE["ts"]   = now
    return results


async def _fetch_yf_market(client: httpx.AsyncClient, display_key: str, yf_sym: str) -> tuple[str, dict] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=1d&range=5d"
    try:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        result = (resp.json().get("chart", {}).get("result") or [None])[0]
        if not result:
            return None
        meta = result["meta"]
        prev  = meta.get("chartPreviousClose") or meta.get("previousClose") or 0
        price = meta.get("regularMarketPrice") or prev
        change = price - prev if prev else 0
        return display_key, {
            "symbol":        display_key,
            "name":          meta.get("shortName") or meta.get("longName") or display_key,
            "price":         round(price, 2),
            "change":        round(change, 2),
            "changePercent": round((change / prev * 100) if prev else 0, 2),
        }
    except Exception:
        return None


@router.get("/world/markets")
async def get_markets() -> dict:
    """Live prices for defense stocks and oil from Yahoo Finance."""
    now = time.time()
    if _MARKETS_CACHE["data"] and now - _MARKETS_CACHE["ts"] < _MARKETS_TTL:
        return _MARKETS_CACHE["data"]

    async with httpx.AsyncClient(headers=_YF_HEADERS) as client:
        tasks = [_fetch_yf_market(client, dk, ys) for dk, ys in _MARKET_TICKERS]
        results_raw = await asyncio.gather(*tasks)

    markets = {key: val for item in results_raw if item for key, val in [item]}
    _MARKETS_CACHE["data"] = markets
    _MARKETS_CACHE["ts"]   = now
    return markets
