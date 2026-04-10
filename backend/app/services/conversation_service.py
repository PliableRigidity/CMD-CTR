import time
import re

import httpx

from backend.app.models.assistant import (
    AgentStatus,
    AssistantRequest,
    AssistantResponse,
    CommandLogEntry,
)
from backend.app.models.maps import RouteRequest
from backend.app.services.action_service import ActionService
from backend.app.services.maps_service import MapsService
from backend.app.services.system_control_service import SystemControlService
from backend.app.services.web_service import WebIntelligenceService
from backend.app.web.schemas.models import SearchRequest
from backend.config import KEEP_ALIVE, OLLAMA_CHAT_URL


class ConversationService:
    def __init__(
        self,
        web_service: WebIntelligenceService | None = None,
        action_service: ActionService | None = None,
        system_control_service: SystemControlService | None = None,
        maps_service: MapsService | None = None,
    ) -> None:
        self.model_name = "qwen2.5:3b"
        self.web_service = web_service
        self.action_service = action_service
        self.system_control_service = system_control_service
        self.maps_service = maps_service

    async def handle(self, request: AssistantRequest) -> AssistantResponse:
        started = time.perf_counter()
        command_response = await self._handle_local_command(request)
        if command_response is not None:
            command_response.processing_time_ms = (time.perf_counter() - started) * 1000
            return command_response

        use_web = self._should_use_web(request)
        sources = []
        payload = {"suggested_mode": "conversation", "web_used": use_web}
        reasoning = "Fast direct response path"

        if use_web and self.web_service is not None:
            search_response = await self.web_service.search(
                SearchRequest(
                    query=request.query,
                    category=request.metadata.get("web_category", "news" if "news" in request.query.lower() else "general"),
                    limit=4,
                )
            )
            sources = self.web_service.to_sources(search_response)
            answer = self._summarize_sources(request.query, sources)
            payload["search_results"] = [item.model_dump() for item in search_response.results]
            reasoning = "Source-aware response generated from live web search results."
        else:
            answer = await self._generate_response(request.query)

        elapsed = (time.perf_counter() - started) * 1000
        return AssistantResponse(
            mode="conversation",
            title="Conversation Mode",
            answer=answer,
            confidence=0.72,
            reasoning=reasoning,
            processing_time_ms=elapsed,
            sources=sources,
            agents=[
                AgentStatus(
                    name="Conversation Core",
                    role="direct_assistant",
                    state="active",
                    confidence=72,
                    summary="Handled through the single-model conversation path.",
                )
            ],
            logs=[
                CommandLogEntry(
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    title="Conversation request",
                    detail=(
                        f"Processed query in conversation mode using model hint {self.model_name}."
                        if not use_web
                        else "Processed query in conversation mode with the web intelligence layer enabled."
                    ),
                )
            ],
            payload=payload,
        )

    async def _handle_local_command(self, request: AssistantRequest) -> AssistantResponse | None:
        raw = request.query.strip()
        lowered = raw.lower()
        if self.action_service is not None:
            open_match = re.match(r"^(open|launch)\s+(.+)$", raw, flags=re.I)
            if open_match:
                target = open_match.group(2).strip()
                if target.lower().startswith("http://") or target.lower().startswith("https://"):
                    result = self.action_service.open_url(target)
                else:
                    result = self.action_service.execute_alias(target)
                return AssistantResponse(
                    mode="conversation",
                    title="Action Result",
                    answer=result.message,
                    confidence=0.9 if result.success else 0.2,
                    reasoning="Handled as a local action command.",
                    processing_time_ms=0,
                    logs=[
                        CommandLogEntry(
                            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            title="Local action",
                            detail=result.message,
                            level="info" if result.success else "error",
                        )
                    ],
                    payload={"action_result": result.model_dump()},
                )

        if self.system_control_service is not None:
            if lowered in {"volume up", "increase volume"}:
                state = self.system_control_service.volume_up()
                return self._audio_response("Volume increased.", state)
            if lowered in {"volume down", "decrease volume"}:
                state = self.system_control_service.volume_down()
                return self._audio_response("Volume decreased.", state)
            if lowered in {"mute", "mute audio", "unmute"}:
                state = self.system_control_service.toggle_mute()
                return self._audio_response("Mute toggled.", state)
            set_match = re.match(r"^(set volume to)\s+(\d{1,3})", lowered)
            if set_match:
                state = self.system_control_service.set_volume(int(set_match.group(2)))
                return self._audio_response(f"Volume set to {state.volume_percent}%.", state)

        if self.maps_service is not None:
            route_match = re.match(r"^(how do i get to|route to|navigate to)\s+(.+)$", lowered)
            if route_match:
                destination = route_match.group(2).strip()
                origin = request.metadata.get("origin") or request.context.get("origin") or "London"
                route = await self.maps_service.get_route(
                    RouteRequest(origin=origin, destination=destination, travel_mode="drive")
                )
                return AssistantResponse(
                    mode="conversation",
                    title="Navigation Result",
                    answer=f"Route from {route.origin} to {route.destination}: {route.distance}, about {route.eta}.",
                    confidence=0.88,
                    reasoning="Handled as a routing command.",
                    processing_time_ms=0,
                    logs=[
                        CommandLogEntry(
                            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            title="Navigation command",
                            detail=f"Computed route from {route.origin} to {route.destination}.",
                        )
                    ],
                    payload={"route": route.model_dump()},
                )

        return None

    def _audio_response(self, message: str, state) -> AssistantResponse:
        return AssistantResponse(
            mode="conversation",
            title="System Control",
            answer=message,
            confidence=0.9,
            reasoning="Handled as a local system control command.",
            processing_time_ms=0,
            logs=[
                CommandLogEntry(
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    title="Audio command",
                    detail=message,
                )
            ],
            payload={"audio_state": state.model_dump()},
        )

    def _should_use_web(self, request: AssistantRequest) -> bool:
        if request.metadata.get("use_web") is True:
            return True
        lowered = request.query.lower()
        keywords = (
            "latest",
            "current",
            "today",
            "news",
            "headline",
            "search",
            "look up",
            "web",
            "website",
            "documentation",
            "docs",
            "recent",
        )
        return any(keyword in lowered for keyword in keywords)

    def _summarize_sources(self, query: str, sources) -> str:
        if not sources:
            return f"I attempted a live web lookup for '{query}', but no readable sources were returned."

        bullets = []
        for source in sources[:3]:
            detail = source.snippet or "No snippet available."
            bullets.append(f"{source.title} ({source.source}): {detail}")
        return "Live web summary:\n- " + "\n- ".join(bullets)

    async def _generate_response(self, query: str) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a local-first personal AI assistant for a futuristic command center. "
                        "Be concise, helpful, and operationally aware."
                    ),
                },
                {"role": "user", "content": query},
            ],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.post(OLLAMA_CHAT_URL, json=payload)
                response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
            if content:
                return content
        except Exception:
            pass

        trimmed = query.strip()
        return (
            f"I've switched into conversation mode for: {trimmed}. "
            "Local conversation scaffolding is active; if Ollama is unavailable, this fallback response keeps the platform usable."
        )
