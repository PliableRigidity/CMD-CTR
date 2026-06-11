from fastapi import APIRouter, Depends, HTTPException, Query

import httpx

from backend.app.api.deps import get_router
from backend.app.models.world import WorldEvent
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.app.world.rss_ingestor import rss_ingestor


router = APIRouter(tags=["world"])

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


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
