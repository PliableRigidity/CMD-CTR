from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

import httpx

from backend.app.web.schemas.models import ArticleDocument

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - fallback if bs4 is unavailable
    BeautifulSoup = None


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class ArticleExtractor:
    async def fetch_article(self, url: str, summarize: bool = True) -> ArticleDocument:
        async with httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "AssistantCommandCenter/1.0"},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        html = response.text
        if BeautifulSoup is not None:
            return self._extract_with_bs4(html, url, summarize)
        return self._extract_with_regex(html, url, summarize)

    def _extract_with_bs4(self, html: str, url: str, summarize: bool) -> ArticleDocument:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "form", "svg", "noscript"]):
            tag.decompose()

        title = self._meta_content(soup, "og:title") or (soup.title.get_text(strip=True) if soup.title else url)
        published = (
            self._meta_content(soup, "article:published_time")
            or self._meta_content(soup, "date")
            or self._meta_content(soup, "pubdate")
        )
        author = self._meta_content(soup, "author")
        image_url = self._meta_content(soup, "og:image")
        language = soup.html.get("lang") if soup.html else None

        main = soup.find("article") or soup.find("main") or soup.body or soup
        paragraphs = [
            _collapse_whitespace(paragraph.get_text(" ", strip=True))
            for paragraph in main.find_all(["p", "li"])
        ]
        paragraphs = [paragraph for paragraph in paragraphs if len(paragraph) > 40]
        content = "\n\n".join(paragraphs[:20])
        excerpt = paragraphs[0] if paragraphs else ""
        summary = self._summarize_text(content or excerpt) if summarize else ""
        return ArticleDocument(
            title=title,
            url=url,
            source=urlparse(url).netloc,
            published_at=published,
            author=author,
            summary=summary,
            content=content,
            excerpt=excerpt,
            language=language,
            image_url=image_url,
        )

    def _extract_with_regex(self, html: str, url: str, summarize: bool) -> ArticleDocument:
        title_match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        title = _collapse_whitespace(unescape(title_match.group(1))) if title_match else url
        text = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = _collapse_whitespace(unescape(text))
        excerpt = text[:320]
        content = text[:5000]
        summary = self._summarize_text(content) if summarize else ""
        return ArticleDocument(
            title=title,
            url=url,
            source=urlparse(url).netloc,
            summary=summary,
            content=content,
            excerpt=excerpt,
        )

    def _meta_content(self, soup, property_name: str) -> str | None:
        tag = soup.find("meta", attrs={"property": property_name}) or soup.find("meta", attrs={"name": property_name})
        if tag and tag.get("content"):
            return _collapse_whitespace(tag["content"])
        return None

    def _summarize_text(self, text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        summary = " ".join(sentence for sentence in sentences[:3] if sentence)
        return summary[:700]
