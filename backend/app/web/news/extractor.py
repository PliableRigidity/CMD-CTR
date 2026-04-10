from __future__ import annotations

import hashlib
import html
import re

from backend.app.web.news.country_resolver import CountryResolver
from backend.app.web.schemas.models import ArticleDocument, NormalizedEvent, SearchResult


CATEGORY_RULES = {
    "politics": ["election", "parliament", "government", "minister", "policy", "president", "prime minister", "nato", "white house"],
    "conflict": ["war", "missile", "strike", "troops", "conflict", "attack", "drone", "ceasefire", "hezbollah"],
    "science": ["research", "scientists", "study", "space", "lab", "artemis", "nasa", "astronomy", "mission"],
    "tech": ["ai", "technology", "software", "chip", "startup", "iphone", "apple", "samsung", "openai"],
    "economy": ["market", "economy", "inflation", "trade", "bank", "tariff", "stocks", "oil", "gold"],
    "environment": ["climate", "storm", "wildfire", "environment", "flood", "earthquake", "typhoon", "hurricane"],
    "sports": ["f1", "formula 1", "grand prix", "football", "tennis", "cricket", "race", "qualifying"],
}

SEVERITY_RULES = {
    "high": ["war", "attack", "crisis", "emergency", "explosion", "death", "sanction", "earthquake", "storm"],
    "medium": ["policy", "trade", "warning", "protest", "outage", "investigation", "regulation"],
}


class EventExtractor:
    def __init__(self) -> None:
        self.country_resolver = CountryResolver()

    def extract_event(self, result: SearchResult, article: ArticleDocument | None = None) -> NormalizedEvent:
        title = self._clean_text(result.title)
        snippet = self._clean_text(result.snippet)
        article_summary = self._clean_text(article.summary if article else "")
        article_content = self._clean_text(article.content[:1600] if article and article.content else "")

        text = " ".join(filter(None, [title, snippet, article_summary, article_content]))
        lowered = text.lower()
        category = self._pick_category(lowered)
        resolution = self.country_resolver.resolve(title, snippet or article_summary, article_content, category)
        severity = self._pick_severity(lowered, category)
        entities = self._extract_entities(text)
        summary = article_summary or snippet or title

        return NormalizedEvent(
            id=hashlib.md5(result.url.encode("utf-8")).hexdigest()[:12],
            title=title,
            url=result.url,
            source=result.source,
            summary=summary,
            country=resolution.display_country,
            primary_country=resolution.primary_country,
            secondary_countries=resolution.secondary_countries,
            region_scope=resolution.region_scope,
            is_global=resolution.is_global,
            region=resolution.region,
            entities=entities,
            category=category,
            severity=severity,
            published_at=article.published_at if article else result.published_at,
            highlight_color=self._highlight_for_category(category, severity),
        )

    def _pick_category(self, lowered: str) -> str:
        scored: list[tuple[str, int]] = []
        for category, keywords in CATEGORY_RULES.items():
            score = sum(1 for keyword in keywords if keyword in lowered)
            if score:
                scored.append((category, score))
        if not scored:
            return "general"
        return sorted(scored, key=lambda item: item[1], reverse=True)[0][0]

    def _pick_severity(self, lowered: str, category: str) -> str:
        for severity, keywords in SEVERITY_RULES.items():
            if any(keyword in lowered for keyword in keywords):
                return severity
        if category in {"conflict", "politics"}:
            return "medium"
        return "low"

    def _extract_entities(self, text: str) -> list[str]:
        entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text)
        deduped: list[str] = []
        for entity in entities:
            if entity not in deduped:
                deduped.append(entity)
        return deduped[:8]

    def _highlight_for_category(self, category: str, severity: str) -> str:
        if severity == "high":
            return "#ff7e8a"
        if category == "economy":
            return "#ffc857"
        if category == "science":
            return "#9cf8d2"
        if category == "sports":
            return "#f7aef8"
        return "#63d2ff"

    def _clean_text(self, value: str) -> str:
        cleaned = html.unescape(value or "")
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = cleaned.replace("\xa0", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()
