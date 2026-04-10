import asyncio
import hashlib
import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx
from pathlib import Path

from backend.app.models.world import WorldEvent
from backend.app.web.news.geography_rules import (
    COUNTRY_KEYWORDS, 
    COUNTRY_REGION_MAP, 
    NON_GEOGRAPHIC_KEYWORDS, 
    GLOBAL_ONLY_KEYWORDS
)
from backend.app.world.text_cleaner import clean_text
from backend.app.world.category_classifier import classifier
from backend.app.world.importance_ranker import ranker

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC News"},
    {"url": "https://www.theguardian.com/world/rss", "source": "The Guardian"},
    {"url": "https://feeds.skynews.com/feeds/rss/world.xml", "source": "Sky News"},
]

# Note: Reuters feed is often blocked without proper headers, so we will use a fallback or standard requests if needed.
# For simplicity, we stick to the ones that are easily accessible, but let's add Reuters.
RSS_FEEDS.append({"url": "https://feeds.reuters.com/reuters/worldNews", "source": "Reuters"})


# Removed CATEGORY_RULES to use category_classifier.py

def load_coordinates():
    coords_path = Path(__file__).parent / "country_coordinates.json"
    if coords_path.exists():
        with open(coords_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

COORDINATES_MAP = load_coordinates()

class RSSIngestor:
    def __init__(self):
        self._cache = []
        self._last_update = None
        
    async def fetch_feed(self, client: httpx.AsyncClient, feed: dict):
        try:
            response = await client.get(feed["url"], timeout=10.0)
            response.raise_for_status()
            return self.parse_xml(response.text, feed["source"])
        except Exception as e:
            logger.warning(f"Failed to fetch {feed['source']}: {e}")
            return []

    def parse_xml(self, xml_content: str, source_name: str):
        events = []
        try:
            root = ET.fromstring(xml_content)
            # Find all item tags
            for item in root.findall(".//item"):
                title = item.findtext("title") or ""
                description = item.findtext("description") or ""
                link = item.findtext("link") or ""
                pubDate = item.findtext("pubDate") or datetime.now(timezone.utc).isoformat()
                
                # Basic cleanup
                title = clean_text(title)
                description = clean_text(description)
                
                if not title:
                    continue
                    
                events.append({
                    "title": title,
                    "summary": description,
                    "link": link,
                    "published_at": pubDate,
                    "source": source_name
                })
        except Exception as e:
            logger.error(f"Error parsing XML for {source_name}: {e}")
        return events

    def deduplicate(self, raw_items):
        seen_urls = set()
        seen_titles = set()
        unique_items = []
        for item in raw_items:
            # Simple deduplication
            title_lower = item["title"].lower()
            if item["link"] in seen_urls or title_lower in seen_titles:
                continue
            seen_urls.add(item["link"])
            seen_titles.add(title_lower)
            unique_items.append(item)
        return unique_items

    # def classify_category removed in favor of category_classifier.py

    def resolve_geography(self, title: str, summary: str):
        text = (title + " " + summary).lower()
        
        # Check explicit global triggers
        if any(kw in text for kw in NON_GEOGRAPHIC_KEYWORDS) or any(kw in text for kw in GLOBAL_ONLY_KEYWORDS):
            return None
            
        country_counts = {}
        for country, keywords in COUNTRY_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in text)
            if count > 0:
                country_counts[country] = count
                
        if not country_counts:
            # Fallback for some common words that usually mean global
            if "world" in text or "global" in text:
                return None
            return None
            
        # Get country with most keyword matches
        primary_country = max(country_counts.items(), key=lambda x: x[1])[0]
        return primary_country

    async def ingest(self) -> list[WorldEvent]:
        # Simple caching for 5 minutes
        now = datetime.now(timezone.utc)
        if self._cache and self._last_update and (now - self._last_update).total_seconds() < 300:
            return self._cache

        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
            tasks = [self.fetch_feed(client, feed) for feed in RSS_FEEDS]
            results = await asyncio.gather(*tasks)
            
        all_raw = []
        for r in results:
            all_raw.extend(r)
            
        unique_items = self.deduplicate(all_raw)
        
        world_events = []
        for item in unique_items:
            classification_result = classifier.classify(item["title"], item["summary"], item["source"])
            category = classification_result["category"]
            
            # Temporary dict for ranker
            doc_for_ranker = {
                "title": item["title"],
                "summary": item["summary"],
                "category": category,
                "source": item["source"],
                "published_at": item["published_at"]
            }
            rank_result = ranker.evaluate(doc_for_ranker)
            
            country = self.resolve_geography(item["title"], item["summary"])
            is_global = country is None
            
            lat, lon = None, None
            if country and country in COORDINATES_MAP:
                lat = COORDINATES_MAP[country].get("lat")
                lon = COORDINATES_MAP[country].get("lon")
            
            event_id = "evt-" + hashlib.md5(item["link"].encode()).hexdigest()[:10]
            
            we = WorldEvent(
                id=event_id,
                title=item["title"],
                country=country or "Global",
                primary_country=country,
                secondary_countries=[],
                region_scope="country" if country else "global",
                is_global=is_global,
                region=COUNTRY_REGION_MAP.get(country, "Global") if country else "Global",
                severity="medium",
                summary=item["summary"],
                tags=[category],
                updated_at=item["published_at"],
                source_name=item["source"],
                source_url=item["link"],
                category=category,
                latitude=lat,
                longitude=lon,
                importance_score=rank_result["importance_score"],
                confidence_score=classification_result["score"],
                freshness_score=rank_result["freshness_score"],
                final_rank=rank_result["final_rank"],
                board_priority=rank_result["board_priority"],
                badge=rank_result["badge"]
            )
            world_events.append(we)
            
        # Sort by final_rank descending
        world_events.sort(key=lambda x: x.final_rank or 0, reverse=True)
            
        self._cache = world_events
        self._last_update = now
        return world_events

rss_ingestor = RSSIngestor()
