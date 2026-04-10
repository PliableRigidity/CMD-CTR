import re

CATEGORY_RULES = {
    "tech": {
        "positive": [
            "ai", "artificial intelligence", "model", "chip", "semiconductor", 
            "software", "openai", "anthropic", "google deepmind", "nvidia", 
            "robotics", "cybersecurity", "cloud computing", "crypto", "bitcoin",
            "smartphone", "social media platform", "computing", "meta", "alphabet"
        ],
        "negative": [
            "immigration", "detention", "asylum", "protest", "humanitarian", 
            "policing", "war casualties", "elections", "parliamentary speeches", 
            "domestic crime", "social policy", "homicide", "police"
        ],
        "weight": 1.2
    },
    "science": {
        "positive": [
            "nasa", "esa", "artemis", "telescope", "exoplanet", "physics", 
            "lab discovery", "biotech breakthrough", "medicine breakthrough", 
            "mission launch", "planetary science", "spacecraft", "spacex", "astronaut",
            "researchers found", "scientists discovered", "cancer treatment"
        ],
        "negative": [
            "gadget", "celebrity science commentary", "smartphone issue",
            "political science", "social science"
        ],
        "weight": 1.1
    },
    "politics": {
        "positive": [
            "parliament", "prime minister", "president", "policy", "legislation", 
            "election", "diplomacy", "treaty", "minister", "government", 
            "white house", "downing street", "cabinet", "senate", "congress", 
            "democrat", "republican", "voters", "ballot", "supreme court", "immigration"
        ],
        "negative": [
            "football manager", "tech regulation only"
        ],
        "weight": 1.0
    },
    "conflict": {
        "positive": [
            "attack", "strike", "military", "missile", "war", "ceasefire", 
            "armed forces", "border conflict", "insurgency", "drone strike", 
            "hezbollah", "hamas", "idf", "nato", "battlefield", "troops", 
            "casualties", "civilian toll", "rebel", "offensive"
        ],
        "negative": [
            "war of words", "price war", "tech war", "culture war", "trade war"
        ],
        "weight": 1.3  # highly prioritized if triggered legitimately
    },
    "environment": {
        "positive": [
            "climate", "wildfire", "flood", "hurricane", "drought", "emissions", 
            "biodiversity", "heatwave", "environmental regulation", "conservation",
            "cop2", "global warming", "carbon", "fossil fuel", "green energy"
        ],
        "negative": [
            "economic climate", "political climate", "business environment"
        ],
        "weight": 1.0
    },
    "sports": {
        "positive": [
            "grand prix", "f1", "qualifying", "race weekend", "driver", 
            "constructor", "team principal", "championship", "football match", 
            "tournament", "premier league", "champions league", "tennis", "olympics"
        ],
        "negative": [
            "political race", "race to build", "economic driver"
        ],
        "weight": 0.8  # only match very strongly if clear
    },
    "economy": {
        "positive": [
            "inflation", "rates", "central bank", "tariffs", "market selloff", 
            "gdp", "trade", "sanctions", "oil shock", "recession", "jobs report",
            "bank of england", "federal reserve", "economy", "investors", "stock market"
        ],
        "negative": [
            "economy of motion"
        ],
        "weight": 1.0
    }
}

class CategoryClassifier:
    def classify(self, title: str, summary: str, source: str) -> dict:
        text = (title + " " + summary).lower()
        scores = {}
        
        for cat, rules in CATEGORY_RULES.items():
            score = 0.0
            
            # Positive keywords
            for pos in rules["positive"]:
                # Use word boundaries or just precise text match
                # Being lenient with basic `in` but boosting exact word matches
                if re.search(rf'\b{re.escape(pos)}\b', text):
                    score += 2.0
                elif pos in text:
                    score += 0.5
            
            # Negative keywords penalty
            for neg in rules["negative"]:
                if re.search(rf'\b{re.escape(neg)}\b', text):
                    score -= 5.0  # Strong penalty
                    
            if score > 0:
                scores[cat] = score * rules["weight"]
            else:
                scores[cat] = 0.0
                
        scores["general"] = 1.0  # baseline
        
        best_cat = max(scores, key=scores.get)
        best_score = scores[best_cat]
        
        # Determine confidence
        confidence = "high"
        if best_cat == "general" or best_score < 2.0:
            best_cat = "general"
            confidence = "low"
            
        return {
            "category": best_cat,
            "raw_scores": scores,
            "confidence": confidence,
            "score": best_score
        }

classifier = CategoryClassifier()
