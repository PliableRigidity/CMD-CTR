from datetime import datetime, timezone

# High signal features indicating a major global event
HIGH_SIGNAL_KEYWORDS = [
    "war", "missile strike", "ceasefire", "summit", "sanctions", "major policy", 
    "export controls", "new ai model", "artemis", "launch milestone", 
    "breakthrough", "climate disaster", "formula 1", "grand prix", 
    "market shock", "interest rate hike", "oil shock", "invasion", "treaty"
]

LOW_SIGNAL_KEYWORDS = [
    "celebrity", "album release", "royal family", "gossip", "lifestyle",
    "opinion", "feature:", "local crime", "domestic incident", "human interest",
    "actor", "actress", "red carpet"
]

SOURCE_WEIGHTS = {
    "Reuters": 1.2,
    "BBC News": 1.1,
    "The Guardian": 1.0,
    "Sky News": 1.0
}

CATEGORY_BASE_IMPORTANCE = {
    "conflict": 8,
    "geopolitics": 7,     # mapped from politics if certain rules hit
    "tech": 6,
    "science": 6,
    "economy": 5,
    "environment": 5,
    "politics": 4,
    "sports": 3,
    "general": 2
}

class ImportanceRanker:
    def evaluate(self, doc: dict) -> dict:
        text = (doc["title"] + " " + doc.get("summary", "")).lower()
        cat = doc.get("category", "general")
        source = doc.get("source", "Unknown")
        
        # 1. Base score by category
        score = CATEGORY_BASE_IMPORTANCE.get(cat, 2)
        
        # 2. Keyword Modifiers
        for kw in HIGH_SIGNAL_KEYWORDS:
            if kw in text:
                score += 3.0
                
        for kw in LOW_SIGNAL_KEYWORDS:
            if kw in text:
                score -= 4.0
                
        # 3. Source Quality Multiplier
        multiplier = SOURCE_WEIGHTS.get(source, 1.0)
        score = score * multiplier
        
        # 4. Freshness
        # Calculate hours ago
        try:
            pub_date = datetime.fromisoformat(doc["published_at"].replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_old = (now - pub_date).total_seconds() / 3600.0
            
            # Decay score slowly over 48 hours
            freshness_score = max(0, 10 - (hours_old / 4.8))
        except:
            freshness_score = 5.0  # fallback
            
        # 5. Final combined rank score
        # Give importance more weight than freshness
        final_rank = (score * 2.0) + freshness_score
        
        # 6. Priority Badge Logic
        badge = None
        if score > 12:
            board_priority = "critical"
            if cat == "conflict": badge = "Active Conflict"
            elif cat == "tech": badge = "Major Tech Shift"
            elif cat == "science": badge = "Space/Science Milestone"
            elif cat == "economy": badge = "Market Shock"
        elif score >= 8:
            board_priority = "high"
        elif score >= 4:
            board_priority = "medium"
        else:
            board_priority = "low"
            
        return {
            "importance_score": round(score, 2),
            "freshness_score": round(freshness_score, 2),
            "final_rank": round(final_rank, 2),
            "board_priority": board_priority,
            "badge": badge
        }

ranker = ImportanceRanker()
