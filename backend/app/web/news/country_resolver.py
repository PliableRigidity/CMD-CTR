from __future__ import annotations

import re
from collections import defaultdict

from backend.app.web.news.geography_rules import (
    COUNTRY_KEYWORDS,
    COUNTRY_REGION_MAP,
    DEFAULT_REGION_OPTIONS,
    F1_VENUE_COUNTRY,
    GLOBAL_ONLY_KEYWORDS,
    NON_GEOGRAPHIC_KEYWORDS,
    SPORTS_KEYWORDS,
)


class CountryResolution:
    def __init__(
        self,
        primary_country: str | None,
        secondary_countries: list[str],
        region_scope: str,
        is_global: bool,
        region: str,
        display_country: str,
    ) -> None:
        self.primary_country = primary_country
        self.secondary_countries = secondary_countries
        self.region_scope = region_scope
        self.is_global = is_global
        self.region = region
        self.display_country = display_country


class CountryResolver:
    def resolve(self, title: str, summary: str, content: str, category: str) -> CountryResolution:
        title_lower = title.lower()
        summary_lower = summary.lower()
        content_lower = content.lower()
        joined = " ".join(part for part in [title_lower, summary_lower, content_lower] if part)

        if category == "sports":
            sports_resolution = self._resolve_sports(joined)
            if sports_resolution is not None:
                return sports_resolution

        if self._is_non_geographic(joined, category):
            return CountryResolution(
                primary_country=None,
                secondary_countries=[],
                region_scope="non-geographic",
                is_global=True,
                region="Global",
                display_country="Global",
            )

        scores: dict[str, float] = defaultdict(float)
        for country, keywords in COUNTRY_KEYWORDS.items():
            for keyword in keywords:
                hits = self._count_keyword(title_lower, keyword)
                if hits:
                    scores[country] += hits * 3.0
                hits = self._count_keyword(summary_lower, keyword)
                if hits:
                    scores[country] += hits * 2.0
                hits = self._count_keyword(content_lower, keyword)
                if hits:
                    scores[country] += hits * 1.0

        ranked = [country for country, score in sorted(scores.items(), key=lambda item: item[1], reverse=True) if score > 0]

        if not ranked:
            return CountryResolution(
                primary_country=None,
                secondary_countries=[],
                region_scope="global",
                is_global=True,
                region="Global",
                display_country="Global",
            )

        primary_country = ranked[0]
        secondary = ranked[1:4]
        region_scope = "regional" if secondary else "country"
        region = COUNTRY_REGION_MAP.get(primary_country, "Global")
        return CountryResolution(
            primary_country=primary_country,
            secondary_countries=secondary,
            region_scope=region_scope,
            is_global=False,
            region=region,
            display_country=primary_country,
        )

    def _resolve_sports(self, lowered: str) -> CountryResolution | None:
        if not any(keyword in lowered for keyword in SPORTS_KEYWORDS):
            return None

        for venue, country in F1_VENUE_COUNTRY.items():
            if venue in lowered:
                return CountryResolution(
                    primary_country=country,
                    secondary_countries=[],
                    region_scope="country",
                    is_global=False,
                    region=COUNTRY_REGION_MAP.get(country, "Global"),
                    display_country=country,
                )
        return None

    def _is_non_geographic(self, lowered: str, category: str) -> bool:
        if category == "science" and any(keyword in lowered for keyword in NON_GEOGRAPHIC_KEYWORDS):
            return True
        if any(keyword in lowered for keyword in GLOBAL_ONLY_KEYWORDS):
            return False
        return False

    def _count_keyword(self, lowered_text: str, keyword: str) -> int:
        keyword = keyword.lower()
        if " " in keyword or "." in keyword:
            return lowered_text.count(keyword)
        return len(re.findall(rf"\b{re.escape(keyword)}\b", lowered_text))

