from __future__ import annotations

import json
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
    "Keep replies to 1-2 sentences — you are speaking aloud, not writing. "
    "CRITICAL: Never answer questions about nodes, IPs, network state, or registered devices from memory or training data. "
    "All node information must come from the registry tools. If asked about a node and no tool result is available, say you need to check the registry."
)

_REMEMBER_RE = re.compile(
    r"(?:remember that|note that|my (?P<key>\w+) is)\s+(?P<value>.+)",
    re.I,
)
_RECALL_RE = re.compile(r"what(?:'s| is) my (\w+)", re.I)

_WEB_TRIGGERS = (
    "latest", "recent", "breaking", "news",
    "what happened", "who won", "current events",
    "search for", "look up", "find out",
    "today's", "right now", "price of", "cost of",
    "how much does", "who is", "tell me about",
)


class ConversationService:
    def __init__(
        self,
        web_service: WebIntelligenceService | None = None,
        action_service: ActionService | None = None,
        system_control_service: SystemControlService | None = None,
        maps_service: MapsService | None = None,
        memory_service: MemoryService | None = None,
        event_service=None,
    ) -> None:
        self.model_name = CONVERSATION_MODEL
        self.web_service = web_service
        self.action_service = action_service
        self.system_control_service = system_control_service
        self.maps_service = maps_service
        self.memory_service = memory_service
        self.event_service = event_service
        self._pending_deletion: str | None = None
        self._pending_ssh: dict | None = None

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

        use_web = request.metadata.get("use_web") is True or self._needs_web(request.query)
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

    async def _emit_tool(self, title: str, detail: str, level: str = "info") -> None:
        if self.event_service:
            await self.event_service.emit(title, detail, level)

    async def _run_tool(self, name: str, args: dict) -> AssistantResponse | None:
        try:
            if name == "get_time":
                await self._emit_tool("[TOOL] get_time", "Fetching local system time")
                data = get_time()
                result = self._render_time_here(data)
                await self._emit_tool("[TOOL] get_time", result)
                return self._simple_response("Time", result)

            if name == "get_time_in":
                place = args.get("place", "").strip()
                await self._emit_tool("[TOOL] get_time_in", f"Looking up time in: {place}")
                try:
                    data = await get_time_in(place)
                    result = self._render_time_there(data)
                    await self._emit_tool("[TOOL] get_time_in", result)
                    return self._simple_response("Time", result)
                except ValueError as ve:
                    err = str(ve)
                    await self._emit_tool("[TOOL] get_time_in", err, "warning")
                    return self._simple_response("Time", err)
                except Exception as fetch_err:
                    err = f"{type(fetch_err).__name__}: {fetch_err}"
                    logger.warning("Time lookup failed for '%s': %s", place, fetch_err)
                    await self._emit_tool("[TOOL] get_time_in", err, "error")
                    return self._simple_response("Time", f"Time lookup failed for {place}.")

            if name == "get_weather":
                place = args.get("place", "").strip()
                await self._emit_tool("[TOOL] get_weather", f"Querying weather: {place}")
                try:
                    data = await get_weather(place)
                    result = self._render_weather(data)
                    await self._emit_tool("[TOOL] get_weather", result)
                    return self._simple_response("Weather", result)
                except RuntimeError as cfg_err:
                    err = str(cfg_err)
                    await self._emit_tool("[TOOL] get_weather", f"Config error: {err}", "error")
                    return self._simple_response("Weather", f"Weather unavailable — {err}.")
                except Exception as fetch_err:
                    err = f"{type(fetch_err).__name__}: {fetch_err}"
                    logger.warning("Weather lookup failed for '%s': %s", place, fetch_err)
                    await self._emit_tool("[TOOL] get_weather", err, "error")
                    return self._simple_response("Weather", f"Weather lookup failed: {type(fetch_err).__name__}.")

            if name == "search_web" and self.web_service is not None:
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] search_web", f"Searching: {query}")
                try:
                    search_resp = await self.web_service.search(
                        SearchRequest(query=query, category=self._infer_search_category(query), limit=5)
                    )
                    sources = self.web_service.to_sources(search_resp)
                    await self._emit_tool("[TOOL] search_web", f"Got {len(sources)} result(s) for: {query}")
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
                    err = f"{type(search_exc).__name__}: {search_exc}"
                    logger.warning("Web search failed for '%s': %s", query, search_exc)
                    await self._emit_tool("[TOOL] search_web", err, "error")
                    return self._simple_response(
                        "Web Search",
                        f"Web search failed ({type(search_exc).__name__}). Using local knowledge only."
                    )

            # ── Node tools ──────────────────────────────────────────────────
            if name == "get_node_ip":
                node_name = args.get("node", "").strip()
                await self._emit_tool("[TOOL] get_node_ip", f"Looking up IP: {node_name}")
                from backend.app.tools.node_tool import resolve_node_ip
                result = resolve_node_ip(node_name)
                await self._emit_tool("[TOOL] get_node_ip", result["summary"], "info" if result["ok"] else "error")
                return self._node_response("Node Lookup", self._render_node_ip(result), result)

            if name == "ping_node":
                node_name = args.get("node", "").strip()
                await self._emit_tool("[TOOL] ping_node", f"Probing: {node_name}")
                from backend.app.tools.node_tool import probe_node_by_name
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, probe_node_by_name, node_name)
                await self._emit_tool("[TOOL] ping_node", result["summary"], "info" if result["ok"] else "warning")
                return self._node_response("Node Probe", self._render_node_probe(result), result)

            if name == "list_nodes":
                await self._emit_tool("[TOOL] list_nodes", "Querying node registry")
                from backend.app.tools.node_tool import list_nodes_status
                result = list_nodes_status()
                await self._emit_tool("[TOOL] list_nodes", result["summary"])
                return self._node_response("Node List", self._render_node_list(result), result)

            if name == "get_node_info":
                node_name = args.get("node", "").strip()
                await self._emit_tool("[TOOL] get_node_info", f"Looking up: {node_name}")
                from backend.app.tools.node_tool import get_node_info
                result = get_node_info(node_name)
                await self._emit_tool("[TOOL] get_node_info", result["summary"], "info" if result["ok"] else "error")
                return self._node_response("Node Info", self._render_node_info(result), result)

            if name == "update_node_ip":
                node_name = args.get("node", "").strip()
                ip = args.get("ip", "").strip()
                await self._emit_tool("[TOOL] update_node_ip", f"Updating {node_name} -> {ip}")
                from backend.app.tools.node_tool import update_node_ip
                result = update_node_ip(node_name, ip)
                await self._emit_tool("[TOOL] update_node_ip", result["summary"], "info" if result["ok"] else "error")
                answer = result["summary"] if result["ok"] else f"Update failed: {result['error']}"
                return self._node_response("Node Updated" if result["ok"] else "Update Failed", answer, result)

            if name == "ssh_node":
                node_name = args.get("node", "").strip()
                username = args.get("username", "").strip()
                if not node_name:
                    return self._simple_response(
                        "SSH",
                        "Which node do you want to SSH into? Say 'ssh into [node name]'.",
                    )
                # Need to resolve IP before asking for username so we can show it
                from backend.app.tools.node_tool import _find_node, _ip_source
                node = _find_node(node_name)
                if not node:
                    await self._emit_tool("[TOOL] ssh_node", f"Node not found: {node_name}", "error")
                    return self._simple_response("SSH Failed", f"Node '{node_name}' not found in registry.")
                ip, source = _ip_source(node)
                host = ip or node.hostname or ""
                if not host or host == "local":
                    await self._emit_tool("[TOOL] ssh_node", f"No address for {node.name}", "error")
                    return self._simple_response(
                        "SSH Failed",
                        f"No IP or hostname configured for '{node.name}'. Add one with 'update {node_name} IP to ...'.",
                    )
                if not username:
                    # Store pending and ask for username
                    self._pending_ssh = {"node": node.name, "host": host, "source": source}
                    await self._emit_tool("[TOOL] ssh_node", f"Awaiting username for {node.name} ({host})", "info")
                    return self._simple_response(
                        "SSH — Username Required",
                        f"Username for {node.name} ({host})? Reply with your username, or 'cancel' to abort.",
                    )
                # Username provided inline — open immediately
                await self._emit_tool("[TOOL] ssh_node", f"Opening SSH: {username}@{host} ({node.name})")
                from backend.app.tools.node_tool import open_ssh_session
                result = open_ssh_session(node_name, username)
                await self._emit_tool("[TOOL] ssh_node", result["summary"], "info" if result["ok"] else "error")
                answer = (
                    f"SSH terminal opened for {node.name} as {username}."
                    if result["ok"]
                    else f"Could not open SSH: {result['error']}"
                )
                return self._node_response("SSH Session" if result["ok"] else "SSH Failed", answer, result)

            if name == "add_node":
                node_name = args.get("node", "").strip()
                hostname = args.get("hostname", "").strip()
                if not node_name:
                    return self._simple_response(
                        "Add Node",
                        "What's the name and address of the node you want to register? "
                        "Say 'add [name] at [hostname or IP]' — for example: 'add laptop at 192.168.1.50'.",
                    )
                await self._emit_tool("[TOOL] add_node", f"Registering: {node_name} ({hostname or 'no address'})")
                from backend.app.tools.node_tool import create_node_entry
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, create_node_entry, node_name, hostname)
                await self._emit_tool("[TOOL] add_node", result["summary"], "info" if result["ok"] else "error")
                answer = result["summary"] if result["ok"] else f"Registration failed: {result['error']}"
                return self._node_response("Node Registered" if result["ok"] else "Registration Failed", answer, result)

            if name == "delete_node":
                node_name = args.get("node", "").strip()
                self._pending_deletion = node_name
                await self._emit_tool("[TOOL] delete_node", f"Confirmation required: delete '{node_name}'", "warning")
                return self._simple_response(
                    "Confirm Delete",
                    f"Delete '{node_name}' from the node registry? This cannot be undone.\n"
                    f"Reply 'yes' or 'yes delete {node_name}' to confirm, or 'cancel' to abort.",
                )

            # ── System / terminal tools ──────────────────────────────────────
            if name == "get_system_specs":
                await self._emit_tool("[TOOL] get_system_specs", "Reading system hardware via psutil + wmic")
                from backend.app.tools.system_tool import get_system_specs
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, get_system_specs)
                await self._emit_tool("[TOOL] get_system_specs", result["summary"], "info" if result["ok"] else "error")
                answer, speech = self._render_system_specs(result)
                return self._system_response("System Specs", answer, speech, result)

            if name == "get_network_info":
                await self._emit_tool("[TOOL] get_network_info", "Reading network interfaces via psutil")
                from backend.app.tools.system_tool import get_network_info
                result = get_network_info()
                await self._emit_tool("[TOOL] get_network_info", result["summary"], "info" if result["ok"] else "error")
                answer, speech = self._render_network_info(result)
                return self._system_response("Network Interfaces", answer, speech, result)

            if name == "get_process_info":
                await self._emit_tool("[TOOL] get_process_info", "Reading process list via psutil")
                from backend.app.tools.system_tool import get_process_info
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, get_process_info)
                await self._emit_tool("[TOOL] get_process_info", result["summary"], "info" if result["ok"] else "error")
                answer, speech = self._render_process_info(result)
                return self._system_response("Process List", answer, speech, result)

            if name == "run_command":
                cmd = args.get("cmd", "").strip()
                if not cmd:
                    return self._simple_response("Terminal", "Which command do you want to run? Say 'run [command]'.")
                await self._emit_tool("[TOOL] run_command", f"$ {cmd}")
                from backend.app.tools.system_tool import run_shell_command
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, run_shell_command, cmd)
                level = "info" if result["ok"] else "error"
                await self._emit_tool("[TOOL] run_command", result["summary"], level)
                answer, speech = self._render_cmd_output(result)
                return self._system_response(f"$ {cmd[:40]}", answer, speech, result)

        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            logger.warning("Tool '%s' failed with args %s: %s", name, args, exc)
            await self._emit_tool(f"[TOOL] {name}", err, "error")

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
            return self._simple_response("Memory Saved", f"I've noted that your {key} is {value}.")

        return None

    async def _handle_local_command(self, request: AssistantRequest) -> AssistantResponse | None:
        raw = request.query.strip()
        lowered = raw.lower()

        # Pending delete confirmation check
        if self._pending_deletion:
            pending = self._pending_deletion
            if re.match(r"^(?:no|cancel|abort|stop|nevermind|nope)[\s\.!]*$", lowered):
                self._pending_deletion = None
                await self._emit_tool("[TOOL] delete_node", f"Cancelled — deletion of '{pending}' aborted", "warning")
                return self._simple_response("Cancelled", f"Deletion of '{pending}' aborted.")
            confirm_re = re.compile(
                rf"^(?:yes|confirm|proceed|do\s+it|affirmative)[\s,\.!]*(?:delete\s+|remove\s+)?(?:{re.escape(pending)})?[\s\.!]*$",
                re.I,
            )
            if confirm_re.match(raw.strip()):
                self._pending_deletion = None
                from backend.app.tools.node_tool import delete_node_by_name
                result = delete_node_by_name(pending)
                await self._emit_tool("[TOOL] delete_node", result["summary"], "info" if result["ok"] else "error")
                answer = result["summary"] if result["ok"] else f"Delete failed: {result['error']}"
                return self._node_response("Node Deleted" if result["ok"] else "Delete Failed", answer, result)

        # Pending SSH username collection
        if self._pending_ssh:
            pending = self._pending_ssh
            if re.match(r"^(?:cancel|abort|no|nevermind|stop)[\s\.!]*$", lowered):
                self._pending_ssh = None
                await self._emit_tool("[TOOL] ssh_node", f"SSH to '{pending['node']}' cancelled", "warning")
                return self._simple_response("SSH Cancelled", f"SSH session to '{pending['node']}' cancelled.")
            # Any valid username (single token, safe chars)
            if re.match(r"^[a-zA-Z0-9_.\-]{1,64}$", raw.strip()):
                username = raw.strip()
                self._pending_ssh = None
                await self._emit_tool("[TOOL] ssh_node", f"Opening SSH: {username}@{pending['host']} ({pending['node']})")
                from backend.app.tools.node_tool import open_ssh_session
                result = open_ssh_session(pending["node"], username)
                await self._emit_tool("[TOOL] ssh_node", result["summary"], "info" if result["ok"] else "error")
                answer = (
                    f"SSH terminal opened for {pending['node']} as {username}."
                    if result["ok"]
                    else f"Could not open SSH: {result['error']}"
                )
                return self._node_response("SSH Session" if result["ok"] else "SSH Failed", answer, result)

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
                    f"I'm not acting as a navigation system anymore. If helpful, I can still help you think through travel options to {destination}.",
                )

        brief_triggers = {
            "brief me", "silvia brief", "status brief", "give me a brief",
            "what's the status", "system status", "mission status",
        }
        if lowered.rstrip("?.") in brief_triggers:
            time_data = get_time()
            answer = (
                f"SILVIA brief. It's {time_data['human']} in {time_data['tz']}. "
                "SILVIA build stability is the priority. Voice systems and infrastructure are under active refinement. "
                "The council is on standby for deeper decisions. All core systems are available."
            )
            return self._simple_response("SILVIA Brief", answer)

        _WORLD_BRIEF_RE = re.compile(
            r"(?:brief\s+me\s+on\s+(?:the\s+)?world|world\s+brief|intel(?:ligence)?\s+brief|"
            r"what(?:'s|\s+is)?\s+(?:happening|going\s+on)\s+(?:in\s+the\s+world|globally|worldwide)|"
            r"world\s+(?:update|news|summary|situation|status)|"
            r"global\s+(?:brief|update|summary|situation))",
            re.I,
        )
        if _WORLD_BRIEF_RE.search(lowered):
            await self._emit_tool("[WORLD] intel_brief", "Pulling top world events for briefing")
            return await self._generate_world_brief()

        return None

    def _node_response(self, title: str, answer: str, result: dict) -> AssistantResponse:
        return AssistantResponse(
            mode="conversation",
            title=title,
            answer=answer,
            confidence=0.97,
            reasoning=f"Node registry tool: {result['tool']}",
            processing_time_ms=0,
            sources=[],
            agents=[AgentStatus(
                name="Node Tool",
                role="network",
                state="complete",
                confidence=97,
                summary=result["summary"],
            )],
            logs=[CommandLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                title=title,
                detail=result["summary"],
                level="info" if result["ok"] else "error",
            )],
            payload={"tool_result": result, "speech_text": sanitize_for_speech(answer)},
        )

    def _render_node_ip(self, result: dict) -> str:
        if not result["ok"]:
            return result["error"] or f"No IP found for {result['node']}."
        d = result["data"]
        source_labels = {"tailscale": "Tailscale", "dns": "DNS", "registry": "Registry", "unknown": "unverified"}
        label = source_labels.get(d.get("source", ""), "unknown")
        verified = d.get("last_verified")
        out = f"{result['node']} — IP: {d['ip']} (source: {label})"
        if verified:
            out += f", last verified {verified}"
        return out + "."

    def _render_node_probe(self, result: dict) -> str:
        if not result["ok"]:
            d = result.get("data") or {}
            err = d.get("probe_error") or result.get("error") or "unreachable"
            return f"{result['node']} is offline. Probe error: {err}."
        d = result.get("data") or {}
        latency = d.get("latency_ms")
        return f"{result['node']} is online" + (f", responding in {latency:.0f}ms" if latency else "") + "."

    def _render_node_list(self, result: dict) -> str:
        nodes = result["data"]["nodes"]
        if not nodes:
            return "No nodes in the registry."
        online = [n["name"] for n in nodes if n["status"] == "online"]
        offline = [n["name"] for n in nodes if n["status"] == "offline"]
        unknown = [n["name"] for n in nodes if n["status"] not in ("online", "offline")]
        parts = []
        if online:
            parts.append(f"Online: {', '.join(online)}")
        if offline:
            parts.append(f"Offline: {', '.join(offline)}")
        if unknown:
            parts.append(f"Unknown: {', '.join(unknown)}")
        return result["summary"] + ". " + ". ".join(parts) + "."

    def _render_node_info(self, result: dict) -> str:
        if not result["ok"]:
            return result["error"] or f"No info for {result['node']}."
        d = result["data"]
        source_labels = {"tailscale": "Tailscale", "dns": "DNS", "registry": "Registry", "unknown": "unverified"}
        label = source_labels.get(d.get("ip_source", ""), "unknown")
        ip_str = f"{d['ip']} ({label} source)" if d.get("ip") else "no IP on record"
        parts = [f"{result['node']} is {d['status']}", f"IP: {ip_str}"]
        if d.get("latency_ms") and d["latency_ms"] > 0.2:
            parts.append(f"latency {d['latency_ms']:.0f}ms")
        if d.get("probe_error"):
            parts.append(f"last error: {d['probe_error']}")
        return ", ".join(parts) + "."

    def _system_response(self, title: str, answer: str, speech: str, result: dict) -> AssistantResponse:
        return AssistantResponse(
            mode="conversation",
            title=title,
            answer=answer,
            confidence=0.99,
            reasoning=f"System tool: {result['tool']}",
            processing_time_ms=0,
            sources=[],
            agents=[AgentStatus(
                name="System Tool",
                role="terminal",
                state="complete",
                confidence=99,
                summary=result["summary"],
            )],
            logs=[CommandLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                title=title,
                detail=result["summary"],
                level="info" if result["ok"] else "error",
            )],
            payload={"tool_result": result, "speech_text": sanitize_for_speech(speech)},
        )

    async def _generate_world_brief(self) -> AssistantResponse:
        try:
            from backend.app.world.rss_ingestor import rss_ingestor
            from backend.app.world.intelligence_service import intelligence_service
            events = await rss_ingestor.ingest()
            top = [e for e in events[:12] if e.board_priority in ("critical", "high", "medium")][:5]
            if not top:
                top = events[:5]
            if not top:
                return self._simple_response("World Brief", "No world events available right now.")

            # Attach any cached assessments
            intelligence_service.attach(top)

            lines = []
            for i, ev in enumerate(top, 1):
                country_label = ev.primary_country or ev.country or "Global"
                priority = (ev.board_priority or "").upper()
                lines.append(f"{i}. [{priority}] {country_label} — {ev.title}")
                if ev.assessment:
                    lines.append(f"   Assessment: {ev.assessment}")
                if ev.prediction:
                    lines.append(f"   Prediction: {ev.prediction}")
                if ev.recommendation:
                    lines.append(f"   Recommendation: {ev.recommendation}")
                if not ev.assessment:
                    lines.append(f"   {(ev.summary or '')[:120].rstrip()}")

            answer = "World Intelligence Brief:\n\n" + "\n".join(lines)
            speech_parts = []
            for ev in top[:3]:
                label = ev.primary_country or "Global"
                assess = ev.assessment or (ev.summary or "")[:80]
                speech_parts.append(f"{label}: {assess}")
            speech = "World brief. " + " — ".join(speech_parts)

            await self._emit_tool("[WORLD] intel_brief", f"{len(top)} events briefed", "info")
            return self._system_response("World Intelligence Brief", answer, speech, {
                "ok": True, "tool": "intel_brief",
                "summary": f"{len(top)} events, {sum(1 for e in top if e.assessment)} with SILVIA assessment",
            })
        except Exception as exc:
            logger.warning("World brief failed: %s", exc)
            return self._simple_response("World Brief", f"Could not retrieve world intelligence: {exc}")

    def _render_system_specs(self, result: dict) -> tuple[str, str]:
        if not result["ok"]:
            msg = f"Could not retrieve system specs: {result['error']}"
            return msg, msg
        d = result["data"]
        cpu = d["cpu"]
        ram = d["ram"]
        disks = d["disk"]
        os_info = d["os"]
        gpu = d.get("gpu") or "unknown"
        lines = [
            f"OS:   {os_info['system']} {os_info['release']} | {os_info['node']}",
            f"CPU:  {(cpu.get('processor') or 'Unknown')[:64]}",
        ]
        cores_str = f"{cpu['cores_physical']} physical / {cpu['cores_logical']} logical"
        freq_str = f" | {cpu['freq_mhz']}MHz" if cpu.get("freq_mhz") else ""
        lines.append(f"      {cores_str}{freq_str} | {cpu['usage_pct']}% current load")
        lines.append(f"RAM:  {ram['total_gb']}GB total | {ram['used_pct']}% used | {ram['available_gb']}GB free")
        lines.append(f"GPU:  {gpu}")
        for disk in disks[:4]:
            lines.append(f"Disk: {disk['device']} — {disk['total_gb']}GB total | {disk['used_pct']}% used | {disk['free_gb']}GB free")
        answer = "\n".join(lines)
        main_disk = disks[0] if disks else None
        disk_speech = f"Main drive is {main_disk['total_gb']}GB at {main_disk['used_pct']}% full." if main_disk else ""
        speech = (
            f"Your system is running {os_info['system']} {os_info['release']} "
            f"with {cpu['cores_logical']} CPU cores and {ram['total_gb']}GB RAM at {ram['used_pct']}% usage. "
            f"GPU is {gpu}. {disk_speech}"
        )
        return answer, speech

    def _render_network_info(self, result: dict) -> tuple[str, str]:
        if not result["ok"]:
            msg = f"Could not retrieve network info: {result['error']}"
            return msg, msg
        interfaces = result["data"]["interfaces"]
        active = [i for i in interfaces if i["is_up"] and i["ipv4"]]
        if not active:
            return "No active network interfaces found.", "No active network interfaces found."
        lines = []
        for iface in active[:8]:
            speed_str = f" | {iface['speed_mbps']}Mbps" if iface.get("speed_mbps") else ""
            lines.append(f"  {iface['name']:<28} {', '.join(iface['ipv4'])}{speed_str}")
        answer = f"Active interfaces ({len(active)}):\n" + "\n".join(lines)
        main_ip = active[0]["ipv4"][0] if active[0]["ipv4"] else "unknown"
        speech = f"You have {len(active)} active network interface{'s' if len(active) != 1 else ''}. Primary IP: {main_ip}."
        return answer, speech

    def _render_process_info(self, result: dict) -> tuple[str, str]:
        if not result["ok"]:
            msg = f"Could not retrieve process list: {result['error']}"
            return msg, msg
        procs = result["data"]["processes"]
        total = result["data"]["total_count"]
        if not procs:
            return f"{total} processes running (all idle).", f"{total} processes running."
        header = f"{'PID':>7}  {'NAME':<28}  {'CPU%':>6}  {'MEM%':>6}"
        sep = "-" * 54
        rows = [
            f"{p['pid']:>7}  {p['name'][:28]:<28}  {p['cpu_pct']:>6.1f}  {p['mem_pct']:>6.2f}"
            for p in procs
        ]
        answer = f"Top processes ({total} total):\n{header}\n{sep}\n" + "\n".join(rows)
        busy = [p for p in procs[:5] if p["cpu_pct"] > 0]
        if busy:
            names = ", ".join(p["name"] for p in busy[:3])
            speech = f"{total} processes running. Top CPU users: {names}."
        else:
            speech = f"{total} processes running, all currently idle."
        return answer, speech

    def _render_cmd_output(self, result: dict) -> tuple[str, str]:
        if not result["ok"] and result["error"] and not result.get("data"):
            msg = f"Command failed: {result['error']}"
            return msg, msg
        d = result.get("data") or {}
        cmd = d.get("cmd", "")
        stdout = d.get("stdout", "")
        stderr = d.get("stderr", "")
        rc = d.get("returncode", -1)
        parts = [f"$ {cmd}"]
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        parts.append(f"[Exit: {rc}]")
        answer = "\n".join(parts)
        first_line = (stdout or stderr or "").split("\n")[0].strip()[:80]
        if result["ok"]:
            speech = f"Command ran successfully. {first_line}" if first_line else "Command completed successfully."
        else:
            speech = f"Command exited with code {rc}. {first_line}" if first_line else f"Command failed with exit code {rc}."
        return answer, speech

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
            return f"I couldn't find any readable live sources for {query}."
        bullets = []
        for source in sources[:3]:
            detail = source.snippet or "No snippet available."
            bullets.append(f"**{source.title}** ({source.source}): {detail}")
        return "**Live web summary:**\n\n" + "\n\n".join(bullets)

    async def _generate_grounded_answer(self, query: str, sources) -> str:
        if not sources:
            return f"I couldn't find any live results for {query}."
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

    def _needs_web(self, query: str) -> bool:
        lowered = query.lower()
        return any(trigger in lowered for trigger in _WEB_TRIGGERS)

    def _persist_turn(self, request: AssistantRequest, answer: str) -> None:
        if self.memory_service:
            self.memory_service.save_turn(request.session_id, request.query, answer, "conversation")

    async def _generate_response_stream(self, query: str, history: list[dict]):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": query})
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 120, "temperature": 0.7, "num_ctx": 2048},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", OLLAMA_CHAT_URL, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.warning("Streaming response failed: %s", exc)
            yield "The local model is unavailable — check that Ollama is running."

    async def handle_stream(self, request: AssistantRequest):
        """
        Async generator for streaming chat responses.
        Emits newline-delimited JSON:
          {"type": "token", "token": "..."}          — LLM token
          {"type": "full", "response": {...}}         — instant tool/action/memory result
          {"type": "done", "speech_text": "...", ...} — stream complete
        """
        started = time.perf_counter()

        memory_response = self._handle_memory_command(request)
        if memory_response is not None:
            self._persist_turn(request, memory_response.answer)
            memory_response.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": memory_response.model_dump()})
            return

        command_response = await self._handle_local_command(request)
        if command_response is not None:
            self._persist_turn(request, command_response.answer)
            command_response.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": command_response.model_dump()})
            return

        use_web = request.metadata.get("use_web") is True or self._needs_web(request.query)
        tool_decision = await plan(request.query, allow_web=use_web)
        if tool_decision.get("action") in ("call_tool", "call_tools"):
            tool_response = await self._execute_plan(tool_decision, request)
            if tool_response is not None:
                self._persist_turn(request, tool_response.answer)
                tool_response.processing_time_ms = (time.perf_counter() - started) * 1000
                yield json.dumps({"type": "full", "response": tool_response.model_dump()})
                return

        # Web path — grounded generation doesn't stream well, return full result
        if use_web and self.web_service is not None:
            from backend.app.web.schemas.models import SearchRequest as _SR
            search_response = await self.web_service.search(
                _SR(
                    query=request.query,
                    category=request.metadata.get("web_category", self._infer_search_category(request.query)),
                    limit=4,
                )
            )
            sources = self.web_service.to_sources(search_response)
            answer = await self._generate_grounded_answer(request.query, sources)
            self._persist_turn(request, answer)
            elapsed = (time.perf_counter() - started) * 1000
            web_resp = AssistantResponse(
                mode="conversation",
                title="Web Search",
                answer=answer,
                confidence=0.85,
                reasoning="Grounded web search response.",
                processing_time_ms=elapsed,
                sources=sources,
                agents=[AgentStatus(name="Web Tool", role="search", state="complete", confidence=85, summary=f"Searched: {request.query}")],
                logs=[CommandLogEntry(timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), title="Web search", detail=f"Query: {request.query}")],
                payload={"speech_text": sanitize_for_speech(answer)},
            )
            yield json.dumps({"type": "full", "response": web_resp.model_dump()})
            return

        # LLM streaming path
        history: list[dict] = []
        if self.memory_service:
            history = self.memory_service.get_ollama_messages(request.session_id, limit=10)

        full_text = ""
        async for token in self._generate_response_stream(request.query, history):
            full_text += token
            yield json.dumps({"type": "token", "token": token})

        if not full_text:
            full_text = "The local model is unavailable — check that Ollama is running."

        self._persist_turn(request, full_text)
        elapsed = (time.perf_counter() - started) * 1000
        yield json.dumps({
            "type": "done",
            "speech_text": sanitize_for_speech(full_text),
            "processing_time_ms": elapsed,
            "agents": [{"name": "Conversation Core", "role": "direct_assistant", "state": "active", "confidence": 72, "summary": "Handled through the streaming conversation path."}],
            "logs": [{"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "title": "Conversation", "detail": f"Streamed with {len(history) // 2} prior turns in {elapsed:.0f}ms."}],
        })

    def _render_time_here(self, data: dict) -> str:
        return f"It's currently {data['human']} in your local timezone ({data['tz']})."

    def _render_time_there(self, data: dict) -> str:
        return f"It's currently {data['human']} in {data['place']} ({data['tz']})."

    def _render_weather(self, data: dict) -> str:
        desc = (data.get("weather_desc") or "clear conditions").replace("-", " ")
        temp = data.get("temperature_c")
        wind = data.get("wind_speed_kmh")
        if temp is None:
            base = f"Here's the latest weather for {data['place']}"
        else:
            base = f"It's currently about {temp:.0f} degrees in {data['place']}"
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
            return f"I couldn't find any live results for {query}."
        lead = sources[0]
        answer = f"Here's the clearest live read on {query}: {lead.title}"
        if lead.snippet:
            answer += f". {lead.snippet}"
        if len(sources) > 1:
            answer += f" I'm also seeing related coverage from {', '.join(source.source for source in sources[1:3])}."
        return answer
