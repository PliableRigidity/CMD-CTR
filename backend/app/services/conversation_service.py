from __future__ import annotations

import logging
import re
import time

import httpx

from backend.app.models.assistant import (
    AgentStatus,
    AssistantRequest,
    AssistantResponse,
    CommandLogEntry,
)
from backend.app.services.action_service import ActionService
from backend.app.services.maps_service import MapsService
from backend.app.services.speech_sanitizer import sanitize_for_speech
from backend.app.services.system_control_service import SystemControlService
from backend.app.services.web_service import WebIntelligenceService
from backend.app.tools.planner import plan
from backend.app.tools.time_tool import get_time, get_time_in
from backend.app.tools.weather import get_weather
from backend.app.web.schemas.models import SearchRequest
from backend.config import CONVERSATION_MODEL
from backend.config import KEEP_ALIVE, OLLAMA_CHAT_URL
from backend.memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are SILVIA, a local-first AI operating system and conversational intelligence partner. "
    "You are calm, professional, conversational, intelligent, concise, and helpful. "
    "You observe, understand, reason, decide, act, and remember. "
    "When the user refers to something said earlier, use the provided conversation history. "
    "Never say you cannot access prior messages because the history is provided to you directly. "
    "Never expose raw tool output, API wording, internal metadata, or implementation jargon. "
    "Always turn facts into natural conversation. "
    "Lead with the direct answer, then add only the most useful supporting detail. "
    "Keep replies to 1-2 sentences — you are speaking aloud, not writing."
)

_REMEMBER_RE = re.compile(
    r"(?:remember that|note that|my (?P<key>\w+) is)\s+(?P<value>.+)",
    re.I,
)
_RECALL_RE = re.compile(r"what(?:'s| is) my (\w+)", re.I)


class ConversationService:
    def __init__(
        self,
        web_service: WebIntelligenceService | None = None,
        action_service: ActionService | None = None,
        system_control_service: SystemControlService | None = None,
        maps_service: MapsService | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.model_name = CONVERSATION_MODEL
        self.web_service = web_service
        self.action_service = action_service
        self.system_control_service = system_control_service
        self.maps_service = maps_service
        self.memory_service = memory_service

    async def handle(self, request: AssistantRequest) -> AssistantResponse:
        started = time.perf_counter()

        def _stamp(response: AssistantResponse) -> AssistantResponse:
            response.processing_time_ms = (time.perf_counter() - started) * 1000
            return response

        def _persist(answer: str) -> None:
            if self.memory_service:
                self.memory_service.save_turn(request.session_id, request.query, answer, "conversation")

        memory_response = self._handle_memory_command(request)
        if memory_response is not None:
            _persist(memory_response.answer)
            return _stamp(memory_response)

        command_response = await self._handle_local_command(request)
        if command_response is not None:
            _persist(command_response.answer)
            return _stamp(command_response)

        use_web = request.metadata.get("use_web") is True
        tool_decision = await plan(request.query, allow_web=use_web)
        if tool_decision.get("action") in ("call_tool", "call_tools"):
            tool_response = await self._execute_plan(tool_decision, request)
            if tool_response is not None:
                _persist(tool_response.answer)
                return _stamp(tool_response)

        history: list[dict] = []
        sources = []

        if use_web and self.web_service is not None:
            search_response = await self.web_service.search(
                SearchRequest(
                    query=request.query,
                    category=request.metadata.get("web_category", self._infer_search_category(request.query)),
                    limit=4,
                )
            )
            sources = self.web_service.to_sources(search_response)
            answer = await self._generate_grounded_answer(request.query, sources)
        else:
            if self.memory_service:
                history = self.memory_service.get_ollama_messages(request.session_id, limit=10)
            answer = await self._generate_response(request.query, history)

        _persist(answer)
        elapsed = (time.perf_counter() - started) * 1000
        return AssistantResponse(
            mode="conversation",
            title="Conversation",
            answer=answer,
            confidence=0.72,
            reasoning="Handled via direct LLM conversation path.",
            processing_time_ms=elapsed,
            sources=sources,
            agents=[AgentStatus(
                name="Conversation Core",
                role="direct_assistant",
                state="active",
                confidence=72,
                summary="Handled through the single-model conversation path.",
            )],
            logs=[CommandLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                title="Conversation",
                detail=f"Processed with {len(history) // 2} prior turns.",
            )],
            payload={"suggested_mode": "conversation", "speech_text": sanitize_for_speech(answer)},
        )

    async def _execute_plan(
        self, decision: dict, request: AssistantRequest
    ) -> AssistantResponse | None:
        action = decision.get("action")

        if action == "call_tool":
            return await self._run_tool(decision.get("name", ""), decision.get("args", {}))

        if action == "call_tools":
            parts: list[str] = []
            sources = []
            for call in decision.get("calls", []):
                result = await self._run_tool(call.get("name", ""), call.get("args", {}))
                if result:
                    parts.append(result.answer)
                    sources.extend(result.sources)
            if parts:
                resp = self._simple_response("Assistant Response", self._combine_tool_answers(parts))
                resp.sources = sources
                return resp

        return None

    async def _run_tool(self, name: str, args: dict) -> AssistantResponse | None:
        try:
            if name == "get_time":
                data = get_time()
                return self._simple_response("Time", self._render_time_here(data))

            if name == "get_time_in":
                place = args.get("place", "").strip()
                try:
                    data = await get_time_in(place)
                    return self._simple_response("Time", self._render_time_there(data))
                except ValueError:
                    return self._simple_response("Time", f"I couldn’t find a timezone for {place}.")
                except Exception as fetch_err:
                    logger.warning("Time lookup failed for '%s': %s", place, fetch_err)
                    return self._simple_response("Time", f"I couldn’t get the current time for {place} just now.")

            if name == "get_weather":
                place = args.get("place", "").strip()
                try:
                    data = await get_weather(place)
                    return self._simple_response("Weather", self._render_weather(data))
                except RuntimeError as cfg_err:
                    return self._simple_response("Weather", str(cfg_err).replace("OPENWEATHER_API_KEY", "the weather service"))
                except Exception as fetch_err:
                    logger.warning("Weather lookup failed for '%s': %s", place, fetch_err)
                    return self._simple_response("Weather", f"I couldn’t get the weather for {place} just now.")

            if name == "search_web" and self.web_service is not None:
                query = args.get("query", "").strip()
                try:
                    search_resp = await self.web_service.search(
                        SearchRequest(query=query, category=self._infer_search_category(query), limit=5)
                    )
                    sources = self.web_service.to_sources(search_resp)
                    answer = await self._generate_grounded_answer(query, sources)
                    return AssistantResponse(
                        mode="conversation",
                        title="Web Search",
                        answer=answer,
                        confidence=0.85,
                        reasoning=f"Tool-routed web search with grounded generation: {query}",
                        processing_time_ms=0,
                        sources=sources,
                        agents=[AgentStatus(
                            name="Web Tool",
                            role="search",
                            state="complete",
                            confidence=85,
                            summary=f"Searched: {query}",
                        )],
                        logs=[CommandLogEntry(
                            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            title="Web search",
                            detail=f"Query: {query}",
                        )],
                        payload={"tool": "search_web", "query": query, "speech_text": sanitize_for_speech(answer)},
                    )
                except Exception as search_exc:
                    logger.warning("Web search failed for '%s': %s", query, search_exc)
                    return self._simple_response(
                        "Web Search",
                        f"Web search is currently unavailable. Here is the best concise answer I can give about {query} from local context."
                    )

        except Exception as exc:
            logger.warning("Tool '%s' failed with args %s: %s", name, args, exc)

        return None

    def _handle_memory_command(self, request: AssistantRequest) -> AssistantResponse | None:
        if self.memory_service is None:
            return None
        raw = request.query.strip()

        recall_match = _RECALL_RE.search(raw)
        if recall_match:
            key = recall_match.group(1).lower()
            value = self.memory_service.recall(key)
            answer = (
                f"Your {key} is {value}."
                if value
                else f"I don't have your {key} stored. Tell me with 'My {key} is ...'."
            )
            return self._simple_response("Memory Recall", answer)

        remember_match = _REMEMBER_RE.search(raw)
        if remember_match:
            key = (remember_match.group("key") or "note").lower()
            value = remember_match.group("value").strip().rstrip(".")
            self.memory_service.remember(key, value)
            return self._simple_response("Memory Saved", f"I’ve noted that your {key} is {value}.")

        return None

    async def _handle_local_command(self, request: AssistantRequest) -> AssistantResponse | None:
        raw = request.query.strip()
        lowered = raw.lower()

        if self.action_service is not None:
            open_match = re.match(r"^(open|launch|start)\s+(.+)$", raw, flags=re.I)
            if open_match:
                target = open_match.group(2).strip()
                if target.lower().startswith("http://") or target.lower().startswith("https://"):
                    result = self.action_service.open_url(target)
                else:
                    result = self.action_service.execute_alias(target)
                return AssistantResponse(
                    mode="conversation",
                    title="Action",
                    answer=result.message,
                    confidence=0.9 if result.success else 0.2,
                    reasoning="Local action command.",
                    processing_time_ms=0,
                    logs=[CommandLogEntry(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        title="Local action",
                        detail=result.message,
                        level="info" if result.success else "error",
                    )],
                    payload={"action_result": result.model_dump(), "speech_text": sanitize_for_speech(result.message)},
                )

        if self.system_control_service is not None:
            if lowered in {"volume up", "increase volume", "louder"}:
                return self._audio_response("Volume increased.", self.system_control_service.volume_up())
            if lowered in {"volume down", "decrease volume", "quieter"}:
                return self._audio_response("Volume decreased.", self.system_control_service.volume_down())
            if lowered in {"mute", "mute audio", "unmute", "silence"}:
                return self._audio_response("Mute toggled.", self.system_control_service.toggle_mute())
            set_match = re.match(r"^set volume to\s+(\d{1,3})", lowered)
            if set_match:
                state = self.system_control_service.set_volume(int(set_match.group(1)))
                return self._audio_response(f"Volume set to {state.volume_percent}%.", state)

        if self.maps_service is not None:
            route_match = re.match(
                r"^(how do i get to|route to|navigate to|directions to)\s+(.+)$", lowered
            )
            if route_match:
                destination = route_match.group(2).strip()
                return self._simple_response(
                    "Assistant Response",
                    f"I’m not acting as a navigation system anymore. If helpful, I can still help you think through travel options to {destination}.",
                )

        brief_triggers = {
            "brief me", "silvia brief", "status brief", "give me a brief",
            "what's the status", "system status", "mission status",
        }
        if lowered.rstrip("?.") in brief_triggers:
            time_data = get_time()
            answer = (
                f"SILVIA brief. It’s {time_data['human']} in {time_data['tz']}. "
                "SILVIA build stability is the priority. Voice systems and infrastructure are under active refinement. "
                "The council is on standby for deeper decisions. All core systems are available."
            )
            return self._simple_response("SILVIA Brief", answer)

        return None

    def _simple_response(self, title: str, answer: str) -> AssistantResponse:
        return AssistantResponse(
            mode="conversation",
            title=title,
            answer=answer,
            confidence=0.95,
            reasoning="Handled by local tool layer.",
            processing_time_ms=0,
            sources=[],
            logs=[CommandLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                title=title,
                detail=answer[:200],
            )],
            payload={"speech_text": sanitize_for_speech(answer)},
        )

    def _audio_response(self, message: str, state) -> AssistantResponse:
        return AssistantResponse(
            mode="conversation",
            title="System Control",
            answer=message,
            confidence=0.9,
            reasoning="Local system control command.",
            processing_time_ms=0,
            logs=[CommandLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                title="Audio",
                detail=message,
            )],
            payload={"audio_state": state.model_dump(), "speech_text": sanitize_for_speech(message)},
        )

    def _summarize_sources(self, query: str, sources) -> str:
        if not sources:
            return f"I couldn’t find any readable live sources for {query}."
        bullets = []
        for source in sources[:3]:
            detail = source.snippet or "No snippet available."
            bullets.append(f"**{source.title}** ({source.source}): {detail}")
        return "**Live web summary:**\n\n" + "\n\n".join(bullets)

    async def _generate_grounded_answer(self, query: str, sources) -> str:
        if not sources:
            return f"I couldn’t find any live results for {query}."
        context_parts = []
        for i, source in enumerate(sources[:4]):
            snippet = (source.snippet or "").strip()
            if snippet:
                context_parts.append(
                    f"[{i+1}] {source.title} | {source.source}"
                    + (f" | {source.published_at}" if source.published_at else "")
                    + f"\n{snippet}"
                )
        if not context_parts:
            return self._summarize_sources(query, sources)
        context = "\n".join(context_parts)
        grounded_prompt = (
            "Using only the search results below, answer the question directly and naturally.\n"
            f"Question: {query}\n\n"
            f"Search results:\n{context}\n\n"
            "Requirements:\n"
            "- If this is a news query, summarize the actual developments instead of telling the user where to look.\n"
            "- Prefer the freshest concrete developments when timestamps are available.\n"
            "- Do not mention tools, APIs, or search mechanics.\n"
            "- If the sources conflict or are weak, say that plainly.\n"
            "- Keep the answer concise, conversational, and useful to hear spoken aloud.\n\n"
            "Answer:"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": grounded_prompt},
        ]
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0.1},
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(OLLAMA_CHAT_URL, json=payload)
                response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
            if content:
                return content
        except Exception as exc:
            logger.warning("Grounded generation failed: %s", exc)
        return self._fallback_source_summary(query, sources)

    async def _generate_response(self, query: str, history: list[dict]) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": query})
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 120, "temperature": 0.7, "num_ctx": 2048},
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(OLLAMA_CHAT_URL, json=payload)
                response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
            if content:
                return content
        except Exception:
            pass
        return (
            f"I've noted your query: {query.strip()}. "
            "The local model is unavailable — check that Ollama is running."
        )

    def _render_time_here(self, data: dict) -> str:
        return f"It’s currently {data['human']} in your local timezone ({data['tz']})."

    def _render_time_there(self, data: dict) -> str:
        return f"It’s currently {data['human']} in {data['place']} ({data['tz']})."

    def _render_weather(self, data: dict) -> str:
        desc = (data.get("weather_desc") or "clear conditions").replace("-", " ")
        temp = data.get("temperature_c")
        wind = data.get("wind_speed_kmh")
        if temp is None:
            base = f"Here’s the latest weather for {data['place']}"
        else:
            base = f"It’s currently about {temp:.0f} degrees in {data['place']}"
        parts = [base]
        if desc:
            parts.append(f"with {desc}")
        if wind is not None:
            breeze = "light" if wind < 15 else "moderate" if wind < 30 else "strong"
            parts.append(f"and a {breeze} breeze around {wind:.0f} kilometers per hour")
        return " ".join(parts).rstrip(".") + "."

    def _combine_tool_answers(self, parts: list[str]) -> str:
        cleaned = [part.strip().rstrip(".") for part in parts if part.strip()]
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return cleaned[0] + "."
        return " ".join(f"{part}." for part in cleaned)

    def _infer_search_category(self, query: str) -> str:
        lowered = query.lower()
        if any(keyword in lowered for keyword in ("latest", "today", "news", "headline", "breaking")):
            return "news"
        return "general"

    def _fallback_source_summary(self, query: str, sources) -> str:
        if not sources:
            return f"I couldn’t find any live results for {query}."
        lead = sources[0]
        answer = f"Here’s the clearest live read on {query}: {lead.title}"
        if lead.snippet:
            answer += f". {lead.snippet}"
        if len(sources) > 1:
            answer += f" I’m also seeing related coverage from {', '.join(source.source for source in sources[1:3])}."
        return answer
