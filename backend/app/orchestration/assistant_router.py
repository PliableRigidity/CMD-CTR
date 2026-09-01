from backend.app.models.assistant import AssistantRequest, AssistantResponse, ModeSelection
from backend.app.services.action_service import ActionService
from backend.app.services.brain63_service import Brain63Service
from backend.app.services.conversation_service import ConversationService
from backend.app.services.decision_service import DecisionService
from backend.app.services.device_manager import DeviceManager
from backend.app.services.event_service import EventService
from backend.app.services.maps_service import MapsService
from backend.app.services.system_control_service import SystemControlService
from backend.app.services.mission_service import MissionService
from backend.app.services.semantic_memory_service import SemanticMemoryService
from backend.app.orchestration.execution_engine import ExecutionEngine
from backend.app.services.web_service import WebIntelligenceService
from backend.app.services.world_events_service import WorldEventsService
from backend.memory.memory_service import MemoryService
from backend.config import BRAIN63_VAULT_PATH


class AssistantPlatformRouter:
    def __init__(self) -> None:
        self.mode_selection = ModeSelection(active_mode="conversation", reason="Default startup mode")
        self.event_service = EventService()
        self.web_service = WebIntelligenceService()
        self.action_service = ActionService()
        self.system_control_service = SystemControlService()
        self.maps_service = MapsService()
        # Voice is optional and expensive to initialise. Keep the core API,
        # persistence and chat available first; initialise voice on first use.
        self.voice_service = _LazyVoiceService()
        self.memory_service = MemoryService()
        self.semantic_memory_service = SemanticMemoryService()
        self.brain63_service = Brain63Service(vault_path=BRAIN63_VAULT_PATH)
        self.conversation_service = ConversationService(
            web_service=self.web_service,
            action_service=self.action_service,
            system_control_service=self.system_control_service,
            maps_service=self.maps_service,
            memory_service=self.memory_service,
            event_service=self.event_service,
            semantic_memory_service=self.semantic_memory_service,
            brain63_service=self.brain63_service,
        )
        self.execution_engine = ExecutionEngine(conversation_service=self.conversation_service)
        self.conversation_service.execution_engine = self.execution_engine
        self.decision_service = DecisionService()
        self.device_manager = DeviceManager()
        self.world_events_service = WorldEventsService()
        self.mission_service = MissionService()

    async def handle(self, request: AssistantRequest) -> AssistantResponse:
        mode = self._resolve_mode(request)
        if mode == "decision":
            # MAGI must never deliberate about a structured project that does
            # not exist. Resolve the entity before invoking any generative path.
            import re
            entity_match = re.search(
                r"\bproject\s+([A-Za-z0-9_-]+)|\b(Project[A-Za-z0-9_-]+)\b|(?:about|for|regarding)\s+(?:the\s+)?([A-Za-z0-9_-]+)\s+project\b",
                request.query,
                re.I,
            )
            if entity_match and re.search(r"\b(?:project|work on|blocking|decid(?:e|ed|ing))\b", request.query, re.I):
                from backend.app.services.project_service import ProjectService
                name = entity_match.group(1) or entity_match.group(2) or entity_match.group(3)
                projects = ProjectService().list_projects()
                found = next((p for p in projects if p.name.lower() == name.lower() or p.id.lower() == name.lower()), None)
                if not found:
                    answer = f"I couldn't find a project called {name}."
                    response = AssistantResponse(mode="decision", title="Project not found", answer=answer,
                                                 confidence=1.0, reasoning="Grounded project registry lookup returned no match.",
                                                 processing_time_ms=0.0)
                    self.memory_service.save_turn(request.session_id, request.query, answer, "decision")
                    return response
            response = await self.decision_service.handle(request)
            # Persist decision exchanges too
            self.memory_service.save_turn(
                request.session_id, request.query, response.answer, "decision"
            )
            return response
        return await self.conversation_service.handle(request)

    def _resolve_mode(self, request: AssistantRequest) -> str:
        if request.mode in {"conversation", "decision"}:
            self.mode_selection = ModeSelection(
                active_mode=request.mode,
                reason="Explicit mode requested by client",
            )
            return request.mode

        lowered = request.query.lower()
        if request.metadata.get("use_web") is True or any(
            keyword in lowered for keyword in ("latest", "current", "today", "news", "search", "web", "docs")
        ):
            self.mode_selection = ModeSelection(
                active_mode="conversation",
                reason="Auto-routed to conversation mode with live web intelligence",
            )
            return "conversation"

        decision_keywords = ("should", "decide", "compare", "best", "tradeoff", "pros", "cons", "evaluate")
        if any(keyword in lowered for keyword in decision_keywords):
            self.mode_selection = ModeSelection(
                active_mode="decision",
                reason="Auto-routed to decision mode based on deliberation keywords",
            )
            return "decision"

        self.mode_selection = ModeSelection(
            active_mode="conversation",
            reason="Auto-routed to conversation mode for direct assistance",
        )
        return "conversation"

    def set_mode(self, mode: str) -> ModeSelection:
        self.mode_selection = ModeSelection(
            active_mode=mode,
            reason="Mode updated by client request",
        )
        self.event_service.emit_nowait("Mode changed", f"Assistant mode switched to {mode}.")
        return self.mode_selection

    def get_mode(self) -> ModeSelection:
        return self.mode_selection


class _LazyVoiceService:
    def __init__(self) -> None:
        self._instance = None

    def _get(self):
        if self._instance is None:
            from backend.app.services.voice_service import VoiceService
            self._instance = VoiceService()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get(), name)
