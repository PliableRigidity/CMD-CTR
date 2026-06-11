import httpx

# Company name → ticker symbol alias map.
# Checked before treating the query string as a raw ticker.
_COMPANY_ALIAS: dict[str, str] = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "facebook": "META",
    "tesla": "TSLA",
    "netflix": "NFLX",
    "nvidia": "NVDA",
    "amd": "AMD",
    "intel": "INTC",
    "qualcomm": "QCOM",
    "broadcom": "AVGO",
    "taiwan semiconductor": "TSM",
    "tsmc": "TSM",
    "samsung": "005930.KS",
    "asml": "ASML",
    "arm": "ARM",
    "palantir": "PLTR",
    "snowflake": "SNOW",
    "salesforce": "CRM",
    "oracle": "ORCL",
    "ibm": "IBM",
    "hp": "HPQ",
    "dell": "DELL",
    "paypal": "PYPL",
    "visa": "V",
    "mastercard": "MA",
    "american express": "AXP",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "goldman sachs": "GS",
    "bank of america": "BAC",
    "citigroup": "C",
    "wells fargo": "WFC",
    "berkshire": "BRK-B",
    "berkshire hathaway": "BRK-B",
    "johnson and johnson": "JNJ",
    "johnson & johnson": "JNJ",
    "pfizer": "PFE",
    "moderna": "MRNA",
    "abbvie": "ABBV",
    "eli lilly": "LLY",
    "unitedhealth": "UNH",
    "cvs": "CVS",
    "walmart": "WMT",
    "target": "TGT",
    "costco": "COST",
    "home depot": "HD",
    "nike": "NKE",
    "disney": "DIS",
    "comcast": "CMCSA",
    "at&t": "T",
    "verizon": "VZ",
    "t-mobile": "TMUS",
    "boeing": "BA",
    "lockheed martin": "LMT",
    "lockheed": "LMT",
    "raytheon": "RTX",
    "northrop grumman": "NOC",
    "northrop": "NOC",
    "general dynamics": "GD",
    "exxon": "XOM",
    "exxonmobil": "XOM",
    "chevron": "CVX",
    "shell": "SHEL",
    "bp": "BP",
    "gold": "GC=F",
    "silver": "SI=F",
    "oil": "CL=F",
    "crude oil": "CL=F",
    "brent": "BZ=F",
    "natural gas": "NG=F",
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    "ethereum": "ETH-USD",
    "eth": "ETH-USD",
    "s&p 500": "^GSPC",
    "s&p": "^GSPC",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow jones": "^DJI",
    "dow": "^DJI",
    "spy": "SPY",
    "qqq": "QQQ",
}

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


async def get_stock_price(query: str) -> dict:
    """
    Resolve a company name or ticker to a Yahoo Finance quote.
    Returns price, change, changePercent, name, marketState, symbol.
    Raises ValueError with a descriptive message on failure.
    """
    key = query.lower().strip()
    ticker = _COMPANY_ALIAS.get(key) or query.upper().strip()

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    try:
        async with httpx.AsyncClient(headers=_YF_HEADERS, timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not reach Yahoo Finance: {exc}") from exc

    data = resp.json()
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        err = data.get("chart", {}).get("error") or {}
        raise ValueError(
            f"Ticker not found: {ticker!r}. "
            f"Try the exact ticker symbol (e.g. AAPL, MSFT). {err.get('description', '')}"
        )

    meta = result.get("meta", {})
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or 0
    price = meta.get("regularMarketPrice") or prev_close
    change = round(price - prev_close, 4) if prev_close else 0
    change_pct = round(change / prev_close * 100, 2) if prev_close else 0
    name = meta.get("shortName") or meta.get("longName") or ticker

    return {
        "ok": True,
        "symbol": ticker,
        "name": name,
        "price": round(price, 2),
        "change": round(change, 2),
        "changePercent": change_pct,
        "marketState": meta.get("marketState", ""),
        "currency": meta.get("currency", "USD"),
        "source": "yahoo_finance",
    }
