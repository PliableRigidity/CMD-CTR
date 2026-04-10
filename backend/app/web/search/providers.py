from __future__ import annotations

import re
from abc import ABC, abstractmethod
from html import unescape
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

import httpx

from backend.app.web.schemas.models import SearchCategory, SearchRequest, SearchResult

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - fallback if bs4 is unavailable
    BeautifulSoup = None


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, request: SearchRequest) -> list[SearchResult]:
        raise NotImplementedError


class DuckDuckGoSearchProvider(SearchProvider):
    def __init__(self) -> None:
        self.base_url = "https://html.duckduckgo.com/html/"

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        query = self._decorate_query(request.query, request.category)
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "AssistantCommandCenter/1.0"},
            follow_redirects=True,
        ) as client:
            response = await client.get(self.base_url, params={"q": query})
            response.raise_for_status()
        return self._parse_results(response.text, request.category, request.limit)

    def _decorate_query(self, query: str, category: SearchCategory) -> str:
        suffix_map = {
            "general": query,
            "news": f"{query} latest news",
            "docs": f"{query} documentation",
            "maps": f"{query} location",
            "tech": f"{query} technology news",
            "science": f"{query} science news",
            "economy": f"{query} economy news",
            "politics": f"{query} politics news",
            "conflict": f"{query} conflict news",
            "environment": f"{query} environment news",
            "sports": f"{query} sports news",
        }
        return suffix_map.get(category, query)

    def _parse_results(self, html: str, category: SearchCategory, limit: int) -> list[SearchResult]:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(".result")
            parsed: list[SearchResult] = []
            for index, card in enumerate(cards[:limit], start=1):
                link = card.select_one(".result__title a") or card.select_one("a.result__a")
                snippet_el = card.select_one(".result__snippet")
                if link is None:
                    continue
                parsed.append(
                    SearchResult(
                        rank=index,
                        title=link.get_text(" ", strip=True),
                        url=self._normalize_url(link.get("href", "")),
                        source=urlparse(self._normalize_url(link.get("href", ""))).netloc or "duckduckgo",
                        snippet=(snippet_el.get_text(" ", strip=True) if snippet_el else ""),
                        category=category,
                        score=max(0.0, 1.0 - ((index - 1) * 0.08)),
                    )
                )
            return parsed

        hrefs = re.findall(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S)
        snippets = re.findall(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>', html, re.I | re.S)
        results: list[SearchResult] = []
        for index, (href, raw_title) in enumerate(hrefs[:limit], start=1):
            title = re.sub(r"<[^>]+>", "", raw_title)
            snippet_raw = ""
            if index - 1 < len(snippets):
                snippet_raw = next((item for item in snippets[index - 1] if item), "")
            snippet = re.sub(r"<[^>]+>", "", snippet_raw)
            url = self._normalize_url(unescape(href))
            results.append(
                SearchResult(
                    rank=index,
                    title=unescape(title).strip(),
                    url=url,
                    source=urlparse(url).netloc or "duckduckgo",
                    snippet=unescape(snippet).strip(),
                    category=category,
                    score=max(0.0, 1.0 - ((index - 1) * 0.08)),
                )
            )
        return results

    def _normalize_url(self, href: str) -> str:
        parsed = urlparse(href)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
            actual = parse_qs(parsed.query).get("uddg", [""])[0]
            return unescape(actual) or href
        return href


class BingRssSearchProvider(SearchProvider):
    def __init__(self) -> None:
        self.base_url = "https://www.bing.com/search"

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        query = request.query
        if request.category == "docs":
            query = f"{query} documentation official docs"
        elif request.category == "maps":
            query = f"{query} location place map"

        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        ) as client:
            response = await client.get(self.base_url, params={"q": query, "format": "rss"})
            response.raise_for_status()
        return self._parse_rss(response.text, request.category, request.limit)

    def _parse_rss(self, xml_text: str, category: SearchCategory, limit: int) -> list[SearchResult]:
        root = ET.fromstring(xml_text)
        results: list[SearchResult] = []
        for index, item in enumerate(root.findall("./channel/item")[:limit], start=1):
            title = item.findtext("title") or "Untitled result"
            url = item.findtext("link") or ""
            snippet = item.findtext("description") or ""
            published = item.findtext("pubDate")
            results.append(
                SearchResult(
                    rank=index,
                    title=title.strip(),
                    url=url.strip(),
                    source=urlparse(url).netloc or "bing",
                    snippet=snippet.strip(),
                    published_at=published.strip() if published else None,
                    category=category,
                    score=self._score_result(index, url, category),
                )
            )
        if category == "docs":
            preferred = [
                result
                for result in results
                if any(
                    token in urlparse(result.url).netloc.lower()
                    for token in ("docs", "developer", "readthedocs", "python.org", "tiangolo", "mozilla.org")
                )
            ]
            if preferred:
                for index, result in enumerate(preferred, start=1):
                    result.rank = index
                return preferred[:limit]
        return results

    def _score_result(self, rank: int, url: str, category: SearchCategory) -> float:
        score = max(0.0, 1.0 - ((rank - 1) * 0.08))
        domain = urlparse(url).netloc.lower()
        if category == "docs" and any(token in domain for token in ("docs", "developer", "readthedocs", "github.io", "tiangolo")):
            score += 0.15
        if category == "maps" and any(token in domain for token in ("google", "tripadvisor", "wikivoyage")):
            score += 0.1
        return min(score, 1.0)


class GoogleNewsRssSearchProvider(SearchProvider):
    def __init__(self) -> None:
        self.base_url = "https://news.google.com/rss/search"

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        ) as client:
            response = await client.get(
                self.base_url,
                params={"q": request.query, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
            )
            response.raise_for_status()
        return self._parse_rss(response.text, request.limit)

    def _parse_rss(self, xml_text: str, limit: int) -> list[SearchResult]:
        root = ET.fromstring(xml_text)
        results: list[SearchResult] = []
        for index, item in enumerate(root.findall("./channel/item")[:limit], start=1):
            title = item.findtext("title") or "Untitled result"
            url = item.findtext("link") or ""
            snippet = item.findtext("description") or ""
            published = item.findtext("pubDate")
            source = "news.google.com"
            source_tag = item.find("source")
            if source_tag is not None and source_tag.text:
                source = source_tag.text.strip()
            results.append(
                SearchResult(
                    rank=index,
                    title=title.strip(),
                    url=url.strip(),
                    source=source,
                    snippet=re.sub(r"<[^>]+>", "", snippet).strip(),
                    published_at=published.strip() if published else None,
                    category="news",
                    score=max(0.0, 1.0 - ((index - 1) * 0.06)),
                )
            )
        return results
