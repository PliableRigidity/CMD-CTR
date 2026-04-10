from backend.app.models.assistant import AssistantRequest, AssistantResponse, ModeSelection
from backend.app.services.action_service import ActionService
from backend.app.services.conversation_service import ConversationService
from backend.app.services.decision_service import DecisionService
from backend.app.services.device_manager import DeviceManager
from backend.app.services.event_service import EventService
from backend.app.services.maps_service import MapsService
from backend.app.services.system_control_service import SystemControlService
from backend.app.services.voice_service import VoiceService
from backend.app.services.web_service import WebIntelligenceService
from backend.app.services.world_events_service import WorldEventsService


class AssistantPlatformRouter:
    def __init__(self) -> None:
        self.mode_selection = ModeSelection(active_mode="conversation", reason="Default startup mode")
        self.event_service = EventService()
        self.web_service = WebIntelligenceService()
        self.action_service = ActionService()
        self.system_control_service = SystemControlService()
        self.maps_service = MapsService()
        self.voice_service = VoiceService()
        self.conversation_service = ConversationService(
            web_service=self.web_service,
            action_service=self.action_service,
            system_control_service=self.system_control_service,
            maps_service=self.maps_service,
        )
        self.decision_service = DecisionService()
        self.device_manager = DeviceManager()
        self.world_events_service = WorldEventsService()

    async def handle(self, request: AssistantRequest) -> AssistantResponse:
        mode = self._resolve_mode(request)
        if mode == "decision":
            return await self.decision_service.handle(request)
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

        decision_keywords = (
            "should",
            "decide",
            "compare",
            "best",
            "tradeoff",
            "pros",
            "cons",
            "evaluate",
        )
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
