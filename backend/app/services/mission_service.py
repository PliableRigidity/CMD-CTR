from __future__ import annotations

from backend.app.models.missions import Mission, MissionRelevance

MISSIONS: list[Mission] = [
    Mission(
        id="alpha", code="ALPHA", name="SILVIA",
        description="Build the personal AI operating system — local-first, Ollama-powered, fully modular.",
        status="active",
        relevance_keywords=["AI", "machine learning", "LLM", "Ollama", "model", "GPU", "CUDA",
                            "neural", "inference", "Python", "FastAPI", "MAGI", "transformer",
                            "Nvidia", "semiconductor", "chip", "compute"],
    ),
    Mission(
        id="beta", code="BETA", name="DroneHive",
        description="Autonomous drone swarm coordination and fleet intelligence platform.",
        status="active",
        relevance_keywords=["drone", "UAV", "UAS", "swarm", "autonomous", "flight", "aviation",
                            "ROS", "robotics", "sensor", "navigation", "GPS", "collision"],
    ),
    Mission(
        id="gamma", code="GAMMA", name="KOI",
        description="AI-native project workflow automation — turns user requirements into structured engineering progress via agent delegation.",
        status="monitoring",
        relevance_keywords=["KOI", "workflow", "agent", "task", "orchestration", "automation",
                            "project manager", "delegation", "pipeline", "requirements",
                            "engineering progress", "multi-agent"],
    ),
    Mission(
        id="delta", code="DELTA", name="University",
        description="Academic coursework, research, and engineering education.",
        status="active",
        relevance_keywords=["university", "research", "paper", "academic", "study", "exam",
                            "thesis", "engineering", "mathematics", "physics", "lab"],
    ),
    Mission(
        id="epsilon", code="EPSILON", name="Brain63",
        description="Personal knowledge base, memory system, and long-term information management.",
        status="active",
        relevance_keywords=["knowledge", "memory", "notes", "obsidian", "PKM", "journal",
                            "productivity", "organisation", "workflow"],
    ),
]

_MISSION_INDEX = {m.id: m for m in MISSIONS}


class MissionService:
    def list_missions(self) -> list[Mission]:
        return MISSIONS

    def get_mission(self, mission_id: str) -> Mission | None:
        return _MISSION_INDEX.get(mission_id)

    def score_event(self, text: str) -> list[MissionRelevance]:
        lower = text.lower()
        results: list[MissionRelevance] = []
        for mission in MISSIONS:
            hits = sum(1 for kw in mission.relevance_keywords if kw.lower() in lower)
            if hits > 0:
                score = min(10, hits * 2)
                results.append(MissionRelevance(
                    mission_id=mission.id,
                    code=mission.code,
                    mission_name=mission.name,
                    score=score,
                ))
        return sorted(results, key=lambda r: r.score, reverse=True)
