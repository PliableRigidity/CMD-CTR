from __future__ import annotations

import json
import logging
import re
import time
from collections import deque

import httpx

from backend.app.models.assistant import (
    AgentStatus,
    AssistantRequest,
    AssistantResponse,
    CommandLogEntry,
)
from backend.app.services.action_service import ActionService
from backend.app.services.command_router import classify, log_route, format_routing_log, format_last_route, strip_wake_prefix, update_last_route
from backend.app.services.maps_service import MapsService
from backend.app.services.capability_verification import (
    CapabilityExecutionResult,
    get_verification_service,
    guard_llm_fallback,
)
from backend.app.services.conversation_state import ConversationState, detect_opener, route_social
from backend.app.services.persona import build_system_prompt, is_builder_topic
from backend.app.services.speech_sanitizer import sanitize_for_speech
from backend.app.services.system_control_service import SystemControlService
from backend.app.services.web_service import WebIntelligenceService
from backend.app.tools.planner import plan
from backend.app.tools.stock_tool import get_stock_price
from backend.app.tools.time_tool import (
    get_time,
    get_time_in,
    resolve_location_to_tz,
    set_user_timezone,
    tz_display_name,
)
from backend.app.tools.weather import get_weather
from backend.app.web.schemas.models import SearchRequest
from backend.config import CONVERSATION_MODEL
from backend.config import KEEP_ALIVE, OLLAMA_CHAT_URL
from backend.memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Persona, tone system, and prompt assembly live in persona.py — single
# source of truth for SILVIA's voice across all LLM paths.

_REMEMBER_RE = re.compile(
    r"(?:remember that|note that|my (?P<key>\w+) is)\s+(?P<value>.+)",
    re.I,
)
_RECALL_RE = re.compile(r"what(?:'s| is) my (\w+)", re.I)

# Statement-intent: the user asserts a belief about a node's state.
# SILVIA verifies it instead of replying with empty acknowledgement.
_NODE_ASSERTION_RE = re.compile(
    r"^(?:i(?:'|’)?m pretty sure|i think|i believe|i bet|i suspect|i(?:'|’)?m sure|pretty sure)\s+"
    r"(?:that\s+)?(?:the\s+)?(?P<node>[a-z0-9_.\-]+)\s+"
    r"(?:is|should be|must be|might be|may be)\s+(?:back\s+)?"
    r"(?P<state>online|offline|up|down|alive|dead|reachable|unreachable)\b",
    re.I,
)

_YES_RE = re.compile(r"^(?:yes|yeah|yep|sure|ok(?:ay)?|go ahead|do it|why not)(?:\s*,?\s*please)?[\s\.!]*$", re.I)

# Phase 17A — approval commands
_APPROVE_RE = re.compile(r"^approve\s+(?P<code>APR-\d+)[\s\.!]*$", re.I)
_REJECT_RE = re.compile(r"^reject\s+(?P<code>APR-\d+)[\s\.!]*$", re.I)
_APPROVE_ALL_RE = re.compile(r"^approve\s+all(?:\s+pending)?[\s\.!]*$", re.I)
_REJECT_ALL_RE = re.compile(r"^reject\s+all(?:\s+pending)?[\s\.!]*$", re.I)

# Phase 17B — workflow commands
_WF_APPROVE_RE = re.compile(r"^approve\s+(?:workflow\s+)?(?P<code>WF-\d+)[\s\.!]*$", re.I)
_WF_REJECT_RE = re.compile(r"^reject\s+(?:workflow\s+)?(?P<code>WF-\d+)[\s\.!]*$", re.I)
_WF_CANCEL_RE = re.compile(r"^cancel\s+(?:workflow\s+)?(?P<code>WF-\d+)[\s\.!]*$", re.I)
_WF_APPROVE_ALL_RE = re.compile(r"^approve\s+all\s+(?:pending\s+)?(?:workflows?|changes?)[\s\.!]*$", re.I)
_WF_REJECT_ALL_RE = re.compile(r"^reject\s+all\s+(?:pending\s+)?(?:workflows?|changes?)[\s\.!]*$", re.I)

# Timezone preference commands — handled locally, no LLM needed.
# SET: "set my timezone to Singapore", "change timezone to London", "switch tz to Tokyo"
_TZ_CHANGE_RE = re.compile(
    r"^(?:set|change|update|switch)\s+(?:my\s+)?(?:time\s*zone|timezone|tz)\s+to\s+(?P<loc>.+?)\s*$",
    re.I,
)
# USE: "use Singapore time", "use UK timezone", "use Eastern time"
_TZ_USE_RE = re.compile(
    r"^use\s+(?P<loc>.+?)\s+(?:time(?:zone)?|tz)\s*$",
    re.I,
)
# QUERY: "what timezone am I using?", "what's my timezone?", "show timezone"
_TZ_QUERY_RE = re.compile(
    r"^(?:"
    r"what(?:'s|\s+is)\s+(?:my\s+)?(?:current\s+)?(?:time\s*zone|timezone|tz)|"
    r"what\s+(?:time\s*zone|timezone|tz)\s+am\s+i\s+(?:using|on|set\s+to)|"
    r"(?:show|get|tell\s+me)\s+(?:my\s+)?(?:time\s*zone|timezone|tz)|"
    r"which\s+(?:time\s*zone|timezone|tz)\s+(?:am\s+i(?:\s+using)?|is\s+(?:set|active))"
    r")\s*\??$",
    re.I,
)

_WEB_TRIGGERS = (
    "latest", "recent", "breaking", "news",
    "what happened", "who won", "current events",
    "search for", "look up", "find out",
    "today's", " today", "right now", "price of", "cost of",
    "how much does", "who is", "tell me about",
    "what does", "what do they", "focus on",  # company/entity profile queries
    " stock", " stocks", "crypto", "market cap",  # financial queries always need live data
)

# Capability self-assessment — SILVIA describing what she can/cannot/would improve.
# Intercepted before the social engine so they get grounded capability-map answers.
_CAP_WHAT_CAN_RE = re.compile(
    r"^(?:what\s+can\s+you\s+(?:actually\s+)?do|what\s+are\s+(?:your\s+)?(?:capabilities?|features?|functions?|abilities?|tools?)|"
    r"what\s+(?:do\s+you\s+)?(?:support|offer)|tell\s+me\s+(?:what\s+you\s+can\s+do|about\s+(?:your\s+)?capabilities?)|"
    r"what\s+are\s+you\s+capable\s+of|show\s+me\s+what\s+you\s+can\s+do)\s*\??$",
    re.I,
)
_CAP_LIMITS_RE = re.compile(
    r"^(?:what\s+can(?:'t|\s+you\s+not)\s+you\s+do|what\s+(?:don'?t|can'?t|cannot)\s+you\s+do|"
    r"what\s+are\s+(?:your\s+)?(?:limitations?|restrictions?|gaps?|weaknesses?)|"
    r"what\s+(?:features?|things?|capabilities?)\s+(?:are\s+)?(?:missing|not\s+(?:implemented|available|there)))\s*\??$",
    re.I,
)
_CAP_IMPROVE_RE = re.compile(
    r"(?:what\s+would\s+you\s+(?:improve|change|add|want|build\s+next|like\s+(?:to\s+have|most))|"
    r"what\s+(?:feature|upgrade|capability)\s+would\s+you\s+(?:want|add|choose|prioritize)|"
    r"what\s+(?:should|would)\s+(?:i|we)\s+(?:build|add|improve|implement)\s+(?:for\s+you|next)|"
    r"what\s+would\s+help\s+you\s+(?:most)?|"
    r"what\s+do\s+you\s+(?:wish\s+you\s+had|want\s+most|need|lack)|"
    r"(?:any|are\s+there\s+any)\s+(?:changes?|improvements?)\s+you(?:'d|\s+would)?\s+(?:like|want|suggest))\s*\??",
    re.I,
)

# "My projects" — must be handled deterministically to prevent LLM from inventing project names.
# The only known projects are in KNOWN_PROJECTS; anything else is hallucinated.
_MY_PROJECTS_RE = re.compile(
    r"^(?:what\s+are\s+)?(?:my\s+)?(?:current\s+)?(?:ongoing\s+)?projects?\s*[\?\.!]?$|"
    r"^(?:list|show|tell\s+me(?:\s+about)?)\s+(?:my\s+)?(?:current\s+)?projects?\s*[\?\.!]?$|"
    r"^what\s+(?:projects?|work)\s+(?:am\s+i|do\s+i)\s+(?:working\s+on|doing|currently\s+(?:working\s+on|doing))\s*[\?\.!]?$",
    re.I,
)

# ---------------------------------------------------------------------------
# Entity registry interceptors
# Queries about known devices/projects must come from the registry, not the LLM.
# ---------------------------------------------------------------------------

# Pattern: all known entity names (devices + projects). Word-boundary aware.
_ENTITY_PAT = r"(?:nighthawk|cyberdeck|drone[\s\-]?hive|koi|brain[\s\-]?63|silvia|cmd[\s\-]?ctr|university)"

# Device hardware/sensor property queries
# "what sensors does nighthawk have?", "does nighthawk have a camera?", "nighthawk hardware"
_DEVICE_PROP_RE = re.compile(
    rf"(?:"
    rf"what\s+(?:sensors?|camera|hardware|specs?|equipment|features?|capabilities?|components?)\s+"
    rf"(?:does|do|has|have)\s+({_ENTITY_PAT})(?:\s+have)?"
    rf"|does\s+({_ENTITY_PAT})\s+(?:have\s+)?(?:a?\s+)?(?:sensor|camera|thermal|imaging|display|gpu)"
    rf"|({_ENTITY_PAT})(?:'s)?\s+(?:sensor|hardware|spec|equipment|feature|component)s?"
    rf"|what\s+(?:sensor|hardware|spec|equipment|feature)s?\s+(?:does|has)\s+({_ENTITY_PAT})"
    rf")\s*\??",
    re.I,
)

# Project status/progress queries
# "what is droneHive working on?", "how is brain63 going?", "status of KOI"
# Note: (?:the\s+)? added to handle "what is the Cyberdeck working on?"
_PROJECT_STATUS_RE = re.compile(
    rf"(?:"
    rf"(?:what\s+(?:is|are)|how\s+(?:is|are))\s+(?:the\s+)?({_ENTITY_PAT})\s+"
    rf"(?:working\s+on|doing|going|progressing?|about|looking|coming\s+(?:along|on|together)|shaping\s+up)"
    rf"|(?:what(?:'s|\s+is)?\s+the\s+)?(?:status|progress|update|state)\s+(?:of|on|for)\s+(?:the\s+)?({_ENTITY_PAT})"
    rf"|({_ENTITY_PAT})\s+(?:status|progress|update|completion)"
    rf")\s*\??",
    re.I,
)

# General entity info: "what is nighthawk?", "tell me about cyberdeck", "describe droneHive"
_ENTITY_INFO_RE = re.compile(
    rf"(?:"
    rf"what\s+(?:is|are)\s+({_ENTITY_PAT})"
    rf"|tell\s+me\s+about\s+(?:the\s+)?({_ENTITY_PAT})"
    rf"|describe\s+(?:the\s+)?({_ENTITY_PAT})"
    rf")\s*\??",
    re.I,
)

# ── LLM pipeline timing (rolling) ──────────────────────────────────────────────
# Each _generate_response_stream call appends a phase-breakdown record here so we
# can see exactly where chat latency goes: context build, the embed/memory search,
# time-to-first-token, and generation throughput.
_LLM_TIMINGS: deque[dict] = deque(maxlen=20)

# Chat latency: "show chat latency" / "llm latency" / "why is silvia slow"
_CHAT_LATENCY_RE = re.compile(
    r"(?:show\s+)?(?:chat|llm|response)\s+latency|llm\s+timing|"
    r"why\s+(?:is\s+)?(?:silvia\s+)?(?:so\s+)?slow|what(?:'s|\s+is)\s+(?:the\s+)?(?:chat|llm)\s+(?:speed|timing)",
    re.I,
)

# ── Deterministic follow-up classifier ────────────────────────────────────────
# Decides whether SILVIA genuinely needs an immediate user reply. Default False.
# A question mark is NOT sufficient — polite closings and open-ended pleasantries
# ("feel free to ask", "anything else?") must NOT trigger follow-up.

# Conversation closers / pleasantries — never require an immediate answer.
_FOLLOWUP_CLOSER_RE = re.compile(
    r"\b(?:"
    r"feel free to (?:ask|reach out|let me know)|just (?:ask|let me know)|"
    r"let me know\b|if you (?:need|have|'?d like|want)\s|"
    r"any(?:thing)?\s+else\b|is there anything else|"
    r"happy to (?:help|assist)|glad to (?:help|assist)|here (?:to help|if you|whenever)|"
    r"my pleasure|you'?re welcome|no problem|no worries|any\s?time\b|"
    r"have a (?:good|great|nice|wonderful)|take care|don'?t hesitate|"
    r"how (?:can|may) i (?:help|assist)|what else (?:can|could|would)"
    r")", re.I,
)

# Explicit follow-up intents (evaluated in priority order).
_FU_MISSING_PARAM_RE = re.compile(
    r"\b(?:which\b.*\bshould i\b|what\b.*\bshould i\b|"
    r"what (?:node|project|file|name|value|reminder|time|date|directory|folder|app|host|target|model|topic)\b|"
    r"please (?:provide|specify|enter|give me|tell me))", re.I,
)
_FU_CHOICE_RE = re.compile(
    r"(?:\bwould you (?:like|prefer)\b.*\bor\b|\bdo you want\b.*\bor\b|"
    r"\bwhich (?:one|of|option|version)\b|\b[\w\-]+\s+or\s+[\w\-]+\s*\?)", re.I,
)
_FU_CONFIRM_RE = re.compile(
    r"\b(?:are you sure|do you want me to (?:delete|remove|cancel|stop|overwrite|clear|reset|disable|send)|"
    r"shall i (?:delete|remove|cancel|send)|confirm\b|is (?:that|this|it) (?:correct|right|ok|okay)|"
    r"y/n|yes\s*/\s*no)", re.I,
)
_FU_APPROVAL_RE = re.compile(
    r"\b(?:should i\b|shall i\b|do you want me to\b|would you like me to\b|may i\b|"
    r"can i (?:go ahead|proceed)|go ahead\?|proceed\?)", re.I,
)
_FU_CLARIFY_RE = re.compile(
    r"\b(?:which\b|what do you mean\b|what exactly\b|whom\b|who\b.*\?|where\b.*\?|when\b.*\?|"
    r"can you (?:clarify|be more specific|elaborate))", re.I,
)
_FU_DIRECT_Q_RE = re.compile(
    r"\b(?:what would you like|what do you (?:want|think)|how does that (?:sound|look)|"
    r"how should we|how do you want|where should we|what'?s next|what next)", re.I,
)


def should_enter_followup(text: str, has_pending: bool = False,
                          pending_kind: str | None = None) -> tuple[bool, str]:
    """Deterministically decide whether a reply needs an immediate user response.

    Returns (expects_reply, followup_reason). Default is (False, "none").
    NOT punctuation-only: a "?" is necessary but not sufficient, and conversation
    closers are excluded even when phrased as questions.
    """
    # A pending confirmation always awaits the user's reply.
    if has_pending:
        return True, (pending_kind or "confirmation")
    if not text or "?" not in text:
        return False, "none"
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    q_sents = [s for s in sentences if s.rstrip().endswith("?")]
    if not q_sents:
        return False, "none"
    for s in q_sents:
        # Strong explicit intents win even if a closer phrase sits nearby.
        if _FU_MISSING_PARAM_RE.search(s):
            return True, "missing_parameter"
        if _FU_CHOICE_RE.search(s):
            return True, "choice"
        if _FU_CONFIRM_RE.search(s):
            return True, "confirmation"
        if _FU_APPROVAL_RE.search(s):
            return True, "approval"
        if _FU_CLARIFY_RE.search(s):
            return True, "clarification"
        if _FU_DIRECT_Q_RE.search(s):
            return True, "clarification"
        # A generic question only counts if it is NOT a conversational closer.
        if not _FOLLOWUP_CLOSER_RE.search(s):
            return True, "clarification"
    return False, "none"


def _followup_explanation(text: str, expects_reply: bool, reason: str, has_pending: bool) -> str:
    if has_pending:
        return f"A pending {reason} is awaiting your response."
    if expects_reply:
        return f"Detected a {reason.replace('_', ' ')} question that needs an answer to continue."
    if text and "?" in text:
        return "A question was present but it is a conversational closer (e.g. 'feel free to ask') — no answer required."
    return "No question or request needing an immediate answer (statement / completed action / polite closing)."


# Last voice follow-up decision (for "show last voice decision").
_LAST_VOICE_DECISION: dict = {}

# "show last voice decision" / "why did silvia keep listening"
_VOICE_DECISION_RE = re.compile(
    r"(?:show\s+)?last\s+voice\s+decision|why\s+did\s+(?:silvia\s+)?(?:keep|stay)\s+listening|"
    r"(?:show\s+)?(?:last\s+)?follow.?up\s+decision",
    re.I,
)

# Voice latency: "show voice latency" / "voice latency" / "how fast is voice"
_VOICE_LATENCY_RE = re.compile(
    r"(?:show\s+)?voice\s+latency|how\s+fast\s+(?:is|was)\s+(?:the\s+)?voice|voice\s+speed|tts\s+latency",
    re.I,
)

# Voice mode: "show voice mode" / "what voice mode" / "current voice mode"
_VOICE_MODE_RE = re.compile(
    r"(?:show|what(?:'?s| is)?|current|which)\s+voice\s+mode|^voice\s+mode\b",
    re.I,
)

# Voice diagnostics: "show voice diagnostics" / "voice diagnostics" / "voice status"
_VOICE_DIAG_RE = re.compile(
    r"(?:show\s+)?voice\s+diag(?:nostics?)?|voice\s+(?:system\s+)?status|voice\s+pipeline\s+status",
    re.I,
)

# TTS diagnostics: "show tts diagnostics" / "tts status" / "voice tts diagnostics"
_TTS_DIAG_RE = re.compile(
    r"show\s+tts\s+diag|tts\s+(?:status|diag)|voice\s+tts\s+diag|"
    r"what\s+is\s+(?:the\s+)?tts\s+(?:doing|status)|tts\s+debug",
    re.I,
)

# Wake word diagnostics: "show wake diagnostics" / "wake word status" / "why isn't the wake word working"
_WAKE_DIAG_RE = re.compile(
    r"(?:show\s+)?wake\s+(?:word\s+)?diag(?:nostics?)?|wake\s+(?:word\s+)?status|"
    r"why\s+(?:isn'?t|does?n'?t)\s+(?:the\s+)?wake\s+(?:word\s+)?work|"
    r"wake\s+word\s+(?:not\s+)?(?:working|broken|stuck|dead|disabled)|"
    r"voice\s+(?:not\s+)?(?:listening|waking|activating)",
    re.I,
)

# Reset wake cooldown: "reset wake cooldown" / "clear wake cooldown" / "wake word stuck"
_WAKE_RESET_RE = re.compile(
    r"reset\s+wake(?:\s+word)?\s+cooldown|clear\s+wake(?:\s+word)?\s+cooldown|"
    r"wake\s+(?:word\s+)?(?:is\s+)?stuck|unstick\s+wake|fix\s+wake\s+word",
    re.I,
)

# User correction: "[entity] is just a Pi NAS" / "[entity] doesn't have a camera"
# Only fires on correction indicators (just/only/actually/doesn't/has no) so
# "nighthawk is online" (state assertion) is NOT caught here.
_USER_CORRECTION_RE = re.compile(
    rf"^(?:"
    rf"({_ENTITY_PAT})\s+is\s+(?:just|only|actually|really)\s+(.+)"
    rf"|(?:no,?\s+)?({_ENTITY_PAT})\s+(?:doesn'?t|does\s+not|has\s+no|isn'?t|is\s+not)\s+(?:have\s+)?(.+)"
    rf")\s*[\.\!]?$",
    re.I,
)

# Brain63 — decision queries: "what did I decide about X", "what's the decision on Y"
_DECISION_QUERY_RE = re.compile(
    rf"(?:"
    rf"what\s+(?:did\s+i|have\s+i)\s+(?:decided?|chosen?|settled?\s+on)\s+(?:about|for|on|regarding)\s+(?:the\s+)?({_ENTITY_PAT}|\w+)"
    rf"|what(?:'s|\s+is)?\s+(?:the\s+)?decision\s+(?:on|for|about|regarding)\s+(?:the\s+)?({_ENTITY_PAT}|\w+)"
    rf"|(?:any\s+)?decisions?\s+(?:on|for|about|regarding)\s+(?:the\s+)?({_ENTITY_PAT}|\w+)"
    rf"|what\s+did\s+(?:i|we)\s+(?:settle\s+on|land\s+on|go\s+with)\s+(?:for|with|on)?\s*({_ENTITY_PAT}|\w+)"
    rf")\s*\??",
    re.I,
)

# Brain63 — roadmap/vision queries: "what's the plan for X", "roadmap for Y"
_ROADMAP_QUERY_RE = re.compile(
    rf"(?:"
    rf"(?:what(?:'s|\s+is)?\s+(?:the\s+)?)?(?:plan|roadmap|phases?|milestones?)\s+(?:for|of)\s+(?:the\s+)?({_ENTITY_PAT}|\w+)"
    rf"|(?:what(?:'s|\s+is)?\s+(?:the\s+)?)?vision\s+(?:for|of|behind)\s+(?:the\s+)?({_ENTITY_PAT}|\w+)"
    rf")\s*\??",
    re.I,
)

# Broad entity mention detection — catches project names in ANY conversational context,
# not just explicit status/info queries. Used to pre-fetch Brain63 context for the LLM.
_ENTITY_DETECT_RE = re.compile(
    r"\b(?:nighthawk|cyberdeck|drone[\s\-]?hive|koi|brain[\s\-]?63|silvia|cmd[\s\-]?ctr|artoo|magi|fpv|university)\b",
    re.I,
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
        semantic_memory_service=None,
        execution_engine=None,
        brain63_service=None,
    ) -> None:
        self.model_name = CONVERSATION_MODEL
        self.web_service = web_service
        self.action_service = action_service
        self.system_control_service = system_control_service
        self.maps_service = maps_service
        self.memory_service = memory_service
        self.event_service = event_service
        self.semantic_memory_service = semantic_memory_service
        self.execution_engine = execution_engine
        self.brain63_service = brain63_service
        self._verification = get_verification_service()
        self._last_tool_ok: bool = True
        self._pending_deletion: str | None = None
        self._pending_ssh: dict | None = None
        self._reminders_paused: bool = False
        self._pending_command: dict | None = None
        self._pending_email: dict | None = None        # Phase 12G — awaiting send confirmation
        self._pending_gcal_delete: dict | None = None  # Phase 12G — awaiting event delete confirmation
        # Soft follow-up offer (e.g. "Want telemetry as well?") — cleared by any
        # input; "yes" executes it. Never used for destructive actions.
        self._pending_suggestion: dict | None = None
        # Debounce for proactive offers so they stay occasional, not constant.
        self._last_suggested: dict[str, float] = {}
        # Conversational continuation state: open threads, opener goals,
        # curiosity cooldowns. See conversation_state.py.
        self.state = ConversationState()
        # Restore persisted timezone preference into the time tool so get_time()
        # immediately uses the right zone without a DB call on every request.
        if self.memory_service:
            stored_tz = self.memory_service.recall("user_timezone")
            if stored_tz:
                set_user_timezone(stored_tz)

    async def handle(self, request: AssistantRequest) -> AssistantResponse:
        started = time.perf_counter()

        def _stamp(response: AssistantResponse) -> AssistantResponse:
            response.processing_time_ms = (time.perf_counter() - started) * 1000
            return response

        def _persist(answer: str) -> None:
            if self.memory_service:
                self.memory_service.save_turn(request.session_id, request.query, answer, "conversation")
            if self.semantic_memory_service:
                import asyncio
                asyncio.create_task(
                    self.semantic_memory_service.embed_and_store(
                        request.session_id, request.query, answer
                    )
                )

        memory_response = self._handle_memory_command(request)
        if memory_response is not None:
            _persist(memory_response.answer)
            return _stamp(memory_response)

        # ── Command Router v2: classify before execution ────────────────────
        _raw_q = strip_wake_prefix(request.query.strip())
        _route = classify(_raw_q)
        log_route(_route)
        await self._emit_tool(
            "[ROUTING]",
            f"Category={_route.category} Owner={_route.owner} Confidence={_route.confidence}%",
        )

        # "show command routing" / "show last route" — display classification log
        if _route.owner == "RoutingLog":
            _is_last = bool(re.match(r"^(?:show\s+)?last\s+route", _raw_q, re.I))
            _rl_text = format_last_route() if _is_last else format_routing_log()
            _persist(_rl_text)
            update_last_route("RoutingLog", "ok")
            return _stamp(self._simple_response("Command Routing", _rl_text))

        # ── Presence Mode (Phase 16C) ─────────────────────────────────────
        from backend.app.services.presence_service import get_presence
        _presence = get_presence()
        _presence_resp = await self._handle_presence_command(_raw_q, _presence, request)
        if _presence_resp is not None:
            _persist(_presence_resp.answer)
            return _stamp(_presence_resp)
        # Record interaction for follow-up window
        _presence._last_interaction = __import__("time").time()
        # ──────────────────────────────────────────────────────────────────

        # ── Context-aware SSH — resolve target from presence when no node in query ──
        if _route.owner == "SSH":
            _ssh_resp = await self._handle_contextual_ssh(_raw_q, _presence, request)
            if _ssh_resp is not None:
                _persist(_ssh_resp.answer)
                return _stamp(_ssh_resp)
        # ──────────────────────────────────────────────────────────────────

        # Pre-social interceptors: capability queries and project queries both produce
        # grounded responses and must not land in the ambiguous-social bucket.
        if _CAP_WHAT_CAN_RE.match(_raw_q) or _CAP_LIMITS_RE.match(_raw_q) or _CAP_IMPROVE_RE.search(_raw_q):
            cap_response = await self._generate_capability_response(_raw_q, request)
            _persist(cap_response.answer)
            return _stamp(cap_response)
        if _MY_PROJECTS_RE.search(_raw_q):
            # Try Brain63 first for grounded retrieval; fall back to static registry.
            _proj_resp = self._projects_from_brain63_or_registry(_raw_q)
            _persist(_proj_resp.answer)
            return _stamp(_proj_resp)

        # Extended project queries: "what are my robotics projects?", category-specific.
        _m_cat_proj = re.match(
            r"^what\s+(?:are\s+)?(?:my\s+)?(\w+)\s+projects?\s*[\?\.!]?$", _raw_q, re.I
        )
        if _m_cat_proj:
            _cat = _m_cat_proj.group(1).lower()
            if _cat not in ("current", "ongoing", "active", "all", "main"):
                _proj_resp = self._projects_from_brain63_or_registry(_raw_q, category=_cat)
                _persist(_proj_resp.answer)
                return _stamp(_proj_resp)

        # Explicit Obsidian/Brain63 knowledge requests must be served from vault directly.
        if re.search(r"\b(?:obsidian|brain\s*63)\b", _raw_q, re.I) and re.search(
            r"(?:projects?|notes?|know|summarize?|what.*know)", _raw_q, re.I
        ):
            _proj_resp = self._projects_from_brain63_or_registry(_raw_q)
            _persist(_proj_resp.answer)
            return _stamp(_proj_resp)

        # Decision queries must be grounded in Brain63 before reaching MAGI/LLM.
        # This prevents the LLM from inventing decisions or note contents.
        _m_dec = _DECISION_QUERY_RE.search(_raw_q)
        if _m_dec:
            _dec_entity = next((g for g in _m_dec.groups() if g), "")
            _dec_answer = self._brain63_entity_answer(_dec_entity, "decisions")
            if _dec_answer:
                _dec_resp = self._grounded_brain63_response("Brain63", _dec_answer)
            else:
                _dec_resp = self._simple_response(
                    "Brain63",
                    f"I have no notes or decision records about '{_dec_entity}' in Brain63. "
                    "I cannot report decisions that aren't recorded in my knowledge base.",
                )
            _persist(_dec_resp.answer)
            return _stamp(_dec_resp)

        # ── Approval commands (Phase 17A — EARLIEST) ────────────────────────
        _apr_resp = await self._handle_approval_command(_raw_q, request)
        if _apr_resp is not None:
            _persist(_apr_resp.answer)
            return _stamp(_apr_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Workflow commands (Phase 17B — before all other fast-paths) ────
        _wf_resp = await self._handle_workflow_command(_raw_q, request)
        if _wf_resp is not None:
            _persist(_wf_resp.answer)
            return _stamp(_wf_resp)

        # ── Workflow fast path (EARLY — before memory + entity handler) ────
        from backend.app.tools.planner import _regex_workflow as _wf_early
        _wf_early_route = _wf_early(_raw_q)
        if _wf_early_route is not None:
            _wf_early_resp = await self._execute_plan(_wf_early_route, request)
            if _wf_early_resp is not None:
                _persist(_wf_early_resp.answer)
                return _stamp(_wf_early_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Memory Provider fast path (EARLY — before memory regex) ───────────
        from backend.app.tools.planner import _regex_memory_provider as _mp_early
        _mp_early_route = _mp_early(_raw_q)
        if _mp_early_route is not None:
            _mp_early_resp = await self._execute_plan(_mp_early_route, request)
            if _mp_early_resp is not None:
                _persist(_mp_early_resp.answer)
                return _stamp(_mp_early_resp)

        # ── Brain Steward fast path (EARLY — before memory regex) ─────────────
        from backend.app.tools.planner import _regex_brain_steward as _bs_early
        _bs_early_route = _bs_early(_raw_q)
        if _bs_early_route is not None:
            _bs_early_resp = await self._execute_plan(_bs_early_route, request)
            if _bs_early_resp is not None:
                _persist(_bs_early_resp.answer)
                return _stamp(_bs_early_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Engineering Memory fast path (EARLY — before entity handler) ─────────
        # "record decision: ...", "show decisions for X", "show project history X"
        # Must run BEFORE _handle_entity_query — entity handler also responds to
        # project names and would return Brain63 context for "show decisions for cyberdeck".
        from backend.app.tools.planner import _regex_memory as _rm_early
        _mem_early = _rm_early(_raw_q)
        if _mem_early is not None:
            _mem_early_resp = await self._execute_plan(_mem_early, request)
            if _mem_early_resp is not None:
                _persist(_mem_early_resp.answer)
                return _stamp(_mem_early_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Workspace Digital Twin fast path (EARLY — before entity handler) ──
        # "what should I buy next for X", "I already bought X for Y", etc.
        # Must run BEFORE _handle_entity_query — entity handler catches project
        # names and routes to raw Brain63 docs instead of reconciled twin state.
        from backend.app.tools.planner import _regex_workspace as _ws_early
        _ws_early_route = _ws_early(_raw_q)
        if _ws_early_route is not None:
            _ws_early_resp = await self._execute_plan(_ws_early_route, request)
            if _ws_early_resp is not None:
                _persist(_ws_early_resp.answer)
                return _stamp(_ws_early_resp)

        # ── Engineering Planner fast path (EARLY — before entity handler) ────
        from backend.app.tools.planner import _regex_planner as _ep_early
        _ep_early_route = _ep_early(_raw_q)
        if _ep_early_route is not None:
            _ep_early_resp = await self._execute_plan(_ep_early_route, request)
            if _ep_early_resp is not None:
                _persist(_ep_early_resp.answer)
                return _stamp(_ep_early_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Entity registry interceptors ───────────────────────────────────────
        # Device/project queries must come from the registry, not the LLM.
        # These run before the social engine — short queries like 'what is nighthawk'
        # would otherwise be absorbed by the ambiguous-social bucket.
        _correction_resp = self._handle_user_correction(_raw_q)
        if _correction_resp is not None:
            _persist(_correction_resp.answer)
            return _stamp(_correction_resp)
        _entity_resp = self._handle_entity_query(_raw_q)
        if _entity_resp is not None:
            _persist(_entity_resp.answer)
            return _stamp(_entity_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Internal Board Router fast path ───────────────────────────────────
        # "open intel board", "go to hardware", "show knowledge graph board", etc.
        # Must run BEFORE route_social() — short navigation commands are ambiguous.
        from backend.app.tools.planner import _regex_board as _rb_pre
        _board_route = _rb_pre(_raw_q)
        if _board_route is not None:
            _board_resp = await self._execute_plan(_board_route, request)
            if _board_resp is not None:
                _persist(_board_resp.answer)
                return _stamp(_board_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Workflow fast path ────────────────────────────────────────────────
        # Must run BEFORE memory fast-path — "show workflows" matches memory's
        # project name regex otherwise.
        from backend.app.tools.planner import _regex_workflow as _wf_pre
        _wf_route = _wf_pre(_raw_q)
        if _wf_route is not None:
            _wf_resp = await self._execute_plan(_wf_route, request)
            if _wf_resp is not None:
                _persist(_wf_resp.answer)
                return _stamp(_wf_resp)

        # ── Memory Provider fast path ─────────────────────────────────────────
        from backend.app.tools.planner import _regex_memory_provider as _mp_pre
        _mp_route = _mp_pre(_raw_q)
        if _mp_route is not None:
            _mp_resp = await self._execute_plan(_mp_route, request)
            if _mp_resp is not None:
                _persist(_mp_resp.answer)
                return _stamp(_mp_resp)

        # ── Brain Steward fast path ───────────────────────────────────────────
        from backend.app.tools.planner import _regex_brain_steward as _bs_pre
        _bs_route = _bs_pre(_raw_q)
        if _bs_route is not None:
            _bs_resp = await self._execute_plan(_bs_route, request)
            if _bs_resp is not None:
                _persist(_bs_resp.answer)
                return _stamp(_bs_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Engineering Memory fast path ───────────────────────────────────────
        # "record decision: ...", "record lesson: ...", "show decisions for X" etc.
        # Must run BEFORE route_social() — "record decision: ..." looks conversational.
        from backend.app.tools.planner import _regex_memory as _rm_pre
        _mem_route = _rm_pre(_raw_q)
        if _mem_route is not None:
            _mem_resp = await self._execute_plan(_mem_route, request)
            if _mem_resp is not None:
                _persist(_mem_resp.answer)
                return _stamp(_mem_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Workspace Digital Twin fast path ──────────────────────────────────
        # "workspace status", "daily briefing", "what should I work on tonight", etc.
        # Must run BEFORE route_social() — short commands look conversational.
        from backend.app.tools.planner import _regex_workspace as _ws_pre
        _ws_route = _ws_pre(_raw_q)
        if _ws_route is not None:
            _ws_resp = await self._execute_plan(_ws_route, request)
            if _ws_resp is not None:
                _persist(_ws_resp.answer)
                return _stamp(_ws_resp)

        from backend.app.tools.planner import _regex_planner as _ep_pre
        _ep_route = _ep_pre(_raw_q)
        if _ep_route is not None:
            _ep_resp = await self._execute_plan(_ep_route, request)
            if _ep_resp is not None:
                _persist(_ep_resp.answer)
                return _stamp(_ep_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Mission Control fast path ──────────────────────────────────────────
        # Phase 9 commands ("morning briefing", "what should I focus on today",
        # "evening review", "stale projects", etc.) are ≤8 words with no command
        # verbs — _is_ambiguous_social() would intercept them as social chat.
        # Dispatch them here, before route_social(), so they reach the tool handlers.
        from backend.app.tools.planner import _regex_mission as _mc_re
        _mc_route = _mc_re(_raw_q)
        if _mc_route is not None:
            _mc_resp = await self._execute_plan(_mc_route, request)
            if _mc_resp is not None:
                _persist(_mc_resp.answer)
                return _stamp(_mc_resp)
        # ──────────────────────────────────────────────────────────────────────

        # ── Diagnostics + Reminder management fast path (before social engine) ──
        _diag_lowered = _raw_q.lower().strip()
        if re.match(r"^(?:deep\s+system\s+check|(?:run\s+)?(?:silvia\s+)?diagnostics|system\s+(?:health|diagnostics)|health\s+check|check\s+all\s+systems)[\s\.\?!]*$", _diag_lowered):
            _diag_resp = await self._run_tool("system_diagnostics", {})
            if _diag_resp:
                _persist(_diag_resp.answer)
                return _stamp(_diag_resp)
        _dismiss_m = re.match(r"^(?:dismiss|stop|silence)\s+reminder\s+(.+)$", _diag_lowered)
        if _dismiss_m:
            _dr = await self._run_tool("dismiss_reminder", {"query": _dismiss_m.group(1).strip()})
            if _dr:
                _persist(_dr.answer)
                return _stamp(_dr)
        if re.match(r"^(?:clear|fix|reset)\s+stuck\s+reminders?$", _diag_lowered):
            _csr = await self._run_tool("clear_stuck_reminders", {})
            if _csr:
                _persist(_csr.answer)
                return _stamp(_csr)
        if re.match(r"^(?:pause|mute|stop(?:\s+all)?)\s+reminders?$", _diag_lowered):
            _pr = await self._run_tool("pause_reminders", {})
            if _pr:
                _persist(_pr.answer)
                return _stamp(_pr)
        if re.match(r"^(?:resume|unpause|unmute)\s+reminders?$", _diag_lowered):
            _rr = await self._run_tool("resume_reminders", {})
            if _rr:
                _persist(_rr.answer)
                return _stamp(_rr)
        if re.match(r"^(?:show\s+)?reminder\s+(?:diagnostics|health|status)$", _diag_lowered):
            _rd = await self._run_tool("show_reminder_diagnostics", {})
            if _rd:
                _persist(_rd.answer)
                return _stamp(_rd)
        if re.match(r"^(?:show\s+)?ssh\s+diagnostics[\s\.\?!]*$", _diag_lowered):
            from backend.app.tools.node_tool import get_ssh_diagnostics
            diag = get_ssh_diagnostics()
            lines = [
                "**SSH Diagnostics**",
                "",
                f"Terminal Provider: {diag['terminal_provider']}",
                f"Windows Terminal: {'Available' if diag['wt_available'] else 'Not found'}"
                + (f" ({diag['wt_path']})" if diag['wt_path'] else ""),
                f"cmd.exe: {'Available' if diag['cmd_available'] else 'Not found'}",
                f"PowerShell: {'Available' if diag['powershell_available'] else 'Not found'}",
                f"SSH client: {'Available' if diag['ssh_available'] else 'Not found'}",
            ]
            last = diag.get("last_launch")
            if last:
                lines += [
                    "",
                    "**Last Launch**",
                    f"Node: {last['node']}",
                    f"Host: {last.get('username', '?')}@{last['host']}",
                    f"Command: `{last['command']}`",
                    f"Provider: {last['provider']}",
                    f"Result: {'Launched' if last['launched'] else 'Failed'}",
                ]
                if last.get("process_id"):
                    lines.append(f"PID: {last['process_id']}")
                if last.get("error"):
                    lines.append(f"Error: {last['error']}")
                lines.append(f"Time: {last['timestamp']}")
            else:
                lines += ["", "No SSH launches in this session."]
            _ssh_diag_text = "\n".join(lines)
            _persist(_ssh_diag_text)
            update_last_route("SSHDiagnostics", "ok")
            return _stamp(self._simple_response("SSH Diagnostics", _ssh_diag_text))
        # ──────────────────────────────────────────────────────────────────────

        # ── Capability Verification Layer ─────────────────────────────────────
        # Intercept infrastructure state queries that would otherwise reach the
        # social LLM or free-text fallback and be hallucinated. Bare commands
        # like "hostname" or "docker ps" after an SSH session must refuse, not
        # fabricate output.
        _infra_refusal = self._verification.intercept_unverified_query(_raw_q)
        if _infra_refusal is not None:
            await self._emit_tool(
                "[VERIFICATION] intercepted",
                f"Refused unverified infrastructure query: {_raw_q}",
                "warning",
            )
            from backend.app.services.execution_ledger import get_ledger
            get_ledger().log_execution(
                intent=_raw_q, tool="verification_guard", status="intercepted",
                message=f"Anti-hallucination: refused '{_raw_q}' — no verified data",
            )
            _persist(_infra_refusal)
            return _stamp(self._simple_response("No Verified Data", _infra_refusal))
        # ──────────────────────────────────────────────────────────────────────

        # ── Social Conversation Engine ─────────────────────────────────────────
        # Runs BEFORE all tool routing. Social messages bypass every tool,
        # every planner call, and Hermes entirely. Conversation is first-class.
        _quick_reply, _social_goal = route_social(_raw_q)

        if _quick_reply is not None:
            _persist(_quick_reply)
            return _stamp(self._simple_response("", _quick_reply))

        if _social_goal is not None:
            history: list[dict] = []
            if self.memory_service:
                history = self.memory_service.get_ollama_messages(request.session_id, limit=10)
            self.state.note_query(
                _raw_q, _social_goal, is_builder=is_builder_topic(_raw_q)
            )
            answer = await self._generate_response(
                _raw_q, history,
                voice=bool(request.metadata.get("voice")),
                goal=_social_goal,
            )
            _persist(answer)
            elapsed = (time.perf_counter() - started) * 1000
            # Attach Brain63 sources when knowledge context was fetched for the LLM.
            _social_b63_sources = self._brain63_sources_for_query(_raw_q)
            return AssistantResponse(
                mode="conversation",
                title="Conversation",
                answer=answer,
                confidence=0.72,
                reasoning=f"Social conversation — goal: {_social_goal}.",
                processing_time_ms=elapsed,
                sources=_social_b63_sources,
                agents=[AgentStatus(
                    name="Conversation Core",
                    role="direct_assistant",
                    state="active",
                    confidence=72,
                    summary="Handled through the social conversation path.",
                )],
                logs=[CommandLogEntry(
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    title="Conversation",
                    detail=f"Social ({_social_goal}) — {len(history) // 2} prior turns.",
                )],
                payload={
                    "suggested_mode": "conversation",
                    "speech_text": sanitize_for_speech(answer),
                },
            )
        # ──────────────────────────────────────────────────────────────────────

        # Operational path — only messages that passed the social engine reach here.
        command_response = await self._handle_local_command(request)
        if command_response is not None:
            _persist(command_response.answer)
            return _stamp(command_response)

        use_web = False

        # Multi-step execution via Hermes
        if self.execution_engine is not None:
            from backend.app.orchestration.execution_engine import is_multistep
            if is_multistep(_raw_q):
                exec_response = await self.execution_engine.run(_raw_q, request)
                if exec_response is not None:
                    _persist(exec_response.answer)
                    return _stamp(exec_response)

        # Web search gated by Command Router — only fires when classified as web_search
        use_web = _route.category == "web_search" or request.metadata.get("use_web") is True
        tool_decision = await plan(_raw_q, allow_web=use_web)
        if tool_decision.get("action") in ("call_tool", "call_tools"):
            tool_response = await self._execute_plan(tool_decision, request)
            if tool_response is not None:
                _persist(tool_response.answer)
                return _stamp(tool_response)

        # ── Anti-hallucination guard (LLM fallback) ────────────────────────
        # Last chance to refuse before the LLM generates a free-text answer.
        # If the query asks for infrastructure facts about a specific node,
        # refuse rather than letting the LLM fabricate an answer.
        _llm_guard = guard_llm_fallback(_raw_q, self._verification)
        if _llm_guard is not None:
            await self._emit_tool(
                "[VERIFICATION] LLM guard",
                f"Blocked LLM fabrication: {_raw_q}",
                "warning",
            )
            from backend.app.services.execution_ledger import get_ledger
            get_ledger().log_execution(
                intent=_raw_q, tool="llm_guard", status="intercepted",
                message=f"Anti-hallucination: blocked LLM answer for '{_raw_q}'",
            )
            _persist(_llm_guard)
            return _stamp(self._simple_response("No Verified Data", _llm_guard))
        # ──────────────────────────────────────────────────────────────────────

        history = []
        sources = []

        if use_web and self.web_service is not None:
            search_response = await self.web_service.search(
                SearchRequest(
                    query=_raw_q,
                    category=request.metadata.get("web_category", self._infer_search_category(_raw_q)),
                    limit=4,
                )
            )
            sources = self.web_service.to_sources(search_response)
            answer = await self._generate_grounded_answer(
                _raw_q, sources, voice=bool(request.metadata.get("voice"))
            )
        else:
            if self.memory_service:
                history = self.memory_service.get_ollama_messages(request.session_id, limit=10)
            self.state.note_query(_raw_q, None, is_builder=is_builder_topic(_raw_q))
            answer = await self._generate_response(
                _raw_q, history, voice=bool(request.metadata.get("voice")),
                goal=None,
            )
            # Attach Brain63 sources when knowledge context was fetched for the LLM.
            _b63_llm_sources = self._brain63_sources_for_query(_raw_q)
            if _b63_llm_sources:
                sources = _b63_llm_sources

        _persist(answer)
        elapsed = (time.perf_counter() - started) * 1000
        return AssistantResponse(
            mode="conversation",
            title="Conversation",
            answer=answer,
            confidence=0.72,
            reasoning="Handled via operational LLM path.",
            processing_time_ms=elapsed,
            sources=sources,
            agents=[AgentStatus(
                name="Conversation Core",
                role="direct_assistant",
                state="active",
                confidence=72,
                summary="Handled through the direct LLM path.",
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
        self._current_intent = request.query  # propagated to ledger via _run_tool
        self._current_session_id = request.session_id  # for approval manager
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
        logger.info("[TOOL] invoking tool=%r args=%r", name, args)
        self._last_tool_ok = True

        # ── Safety gate (Phase 17A/17B) ────────────────────────────────────
        if not getattr(self, "_bypass_safety", False):
            try:
                from backend.app.services.safety_engine import get_safety_engine
                gate = get_safety_engine().gate(name, args, query=self._current_intent or "")
                if gate.get("blocked"):
                    await self._emit_tool("[SAFETY] blocked", f"{name}: {gate.get('block_reason', '')}", "warning")
                    return self._simple_response("Action Blocked", f"This action is not allowed under the current policy.\n\n{gate.get('block_reason', '')}")
                if gate.get("requires_approval"):
                    session_id = getattr(self, "_current_session_id", "")
                    # Phase 17B: create a structured workflow instead of a simple approval
                    wf_category = self._get_workflow_category(name)
                    from backend.app.services.workflow_engine import get_workflow_engine
                    wf_title = self._build_workflow_title(name, args)
                    wf_desc = self._build_workflow_description(name, args)
                    wf = get_workflow_engine().create(
                        category=wf_category,
                        title=wf_title,
                        description=wf_desc,
                        risk_level=gate["risk_name"],
                        tool_name=name,
                        tool_args=args,
                        affected=[args.get("node", args.get("project", args.get("name", "")))],
                        project=args.get("project", ""),
                        session_id=session_id,
                        auto_submit=True,
                    )
                    await self._emit_tool("[WORKFLOW] created", f"{wf['code']}: {name}", "warning")
                    return self._render_workflow_card(wf)
            except Exception as safety_err:
                logger.debug("Safety gate error (proceeding): %s", safety_err)
        # ─────────────────────────────────────────────────────────────────

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

            if name == "get_stock_price":
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] get_stock_price", f"Fetching quote: {query}")
                try:
                    data = await get_stock_price(query)
                    result = self._render_stock(data)
                    await self._emit_tool("[TOOL] get_stock_price", result)
                    return self._simple_response("Markets", result)
                except ValueError as ve:
                    err = str(ve)
                    await self._emit_tool("[TOOL] get_stock_price", err, "warning")
                    return self._simple_response("Markets", err)
                except Exception as fetch_err:
                    err = f"{type(fetch_err).__name__}: {fetch_err}"
                    logger.warning("Stock lookup failed for '%s': %s", query, fetch_err)
                    await self._emit_tool("[TOOL] get_stock_price", err, "error")
                    return self._simple_response("Markets", f"Stock lookup failed for {query}.")

            if name == "search_web":
                if self.web_service is None:
                    await self._emit_tool("[TOOL] search_web", "Web search unavailable — SEARXNG_URL not configured", "error")
                    return self._simple_response(
                        "Web Search Unavailable",
                        "Live web search is not configured. Set SEARXNG_URL in .env to enable news, current events, and real-time data. I won't answer current-information queries from model knowledge — the information would be stale.",
                    )
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
                self._last_tool_ok = result["ok"]
                self._verification.record_result(CapabilityExecutionResult(
                    success=result["ok"], executed=True, source="probe",
                    raw_output=result.get("summary", ""),
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    node=node_name, capability="ping", tool="ping_node",
                ))
                answer = self._render_node_probe(result)
                if result["ok"]:
                    offer = self._maybe_suggest("probe_telemetry", " Want telemetry as well?")
                    if offer:
                        answer += offer
                        self._pending_suggestion = {"action": "telemetry", "node": result.get("node") or node_name}
                return self._node_response("Node Probe", answer, result)

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

            if name == "verify_node":
                node_name = args.get("node", "").strip()
                await self._emit_tool("[TOOL] verify_node", f"Verifying: {node_name}")
                from backend.app.tools.node_tool import verify_node_by_name
                result = await verify_node_by_name(node_name)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] verify_node", result["summary"], level)
                return self._node_response(
                    "Node Verified" if result["ok"] else "Verification Failed",
                    self._render_verification(result),
                    result,
                )

            if name == "refresh_nodes":
                await self._emit_tool("[TOOL] refresh_nodes", "Verifying all registered nodes")
                from backend.app.tools.node_tool import verify_all_nodes
                result = await verify_all_nodes()
                await self._emit_tool("[TOOL] refresh_nodes", result["summary"], "info")
                return self._node_response("Node Verification", self._render_refresh(result), result)

            if name == "get_node_telemetry":
                node_name = args.get("node", "").strip()
                label = node_name if node_name and node_name != "all" else "all nodes"
                await self._emit_tool("[TOOL] get_node_telemetry", f"Reading telemetry: {label}")
                from backend.app.tools.node_tool import get_node_telemetry
                result = get_node_telemetry(node_name)
                await self._emit_tool("[TOOL] get_node_telemetry", result["summary"], "info" if result["ok"] else "error")
                return self._node_response("Node Telemetry", self._render_node_telemetry(result), result)

            if name == "get_watch_alerts":
                await self._emit_tool("[TOOL] get_watch_alerts", "Fetching active Watch Officer alerts")
                from backend.app.tools.node_tool import get_watch_alerts
                result = get_watch_alerts()
                await self._emit_tool("[TOOL] get_watch_alerts", result["summary"], "info")
                return self._node_response("Watch Officer", self._render_watch_alerts(result), result)

            # ── Personal ops ──────────────────────────────────────────────────
            if name == "set_reminder":
                raw = args.get("raw", "").strip()
                await self._emit_tool("[TOOL] set_reminder", f"Parsing reminder: {raw[:60]}")
                from backend.app.tools.personal_tool import set_reminder
                result = set_reminder(raw)
                await self._emit_tool("[TOOL] set_reminder", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response("Reminder Set" if result["ok"] else "Reminder Error",
                                               self._render_reminder_set(result), result)

            if name == "list_reminders":
                await self._emit_tool("[TOOL] list_reminders", "Fetching active reminders")
                from backend.app.tools.personal_tool import list_reminders
                result = list_reminders()
                await self._emit_tool("[TOOL] list_reminders", result["summary"])
                return self._personal_response("Reminders", self._render_reminder_list(result), result)

            if name == "delete_reminder":
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] delete_reminder", f"Deleting reminder: {query}")
                from backend.app.tools.personal_tool import delete_reminder
                result = delete_reminder(query)
                await self._emit_tool("[TOOL] delete_reminder", result["summary"], "info" if result["ok"] else "warning")
                answer = result["summary"] if result["ok"] else f"Reminder not found: {query}"
                return self._personal_response("Reminder Deleted" if result["ok"] else "Not Found", answer, result)

            if name == "complete_reminder":
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] complete_reminder", f"Completing reminder: {query}")
                from backend.app.tools.personal_tool import complete_reminder as _complete_reminder
                result = _complete_reminder(query)
                await self._emit_tool("[TOOL] complete_reminder", result["summary"], "info" if result["ok"] else "warning")
                answer = result["summary"] if result["ok"] else f"Reminder not found: {query}"
                return self._personal_response("Reminder Done" if result["ok"] else "Not Found", answer, result)

            if name == "dismiss_reminder":
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] dismiss_reminder", f"Dismissing reminder: {query}")
                from backend.app.services.reminder_service import ReminderService
                from backend.app.services.watch_service import WatchService
                rs = ReminderService()
                reminder = rs.find_by_query(query)
                if not reminder:
                    return self._simple_response("Not Found", f"No active reminder matching '{query}'.")
                rs.complete_reminder(reminder.id)
                ws = WatchService()
                ws.resolve_alert(f"reminder:{reminder.id}")
                ws.resolve_alert(f"reminder:{reminder.id}:escalated")
                ws.resolve_alert(f"reminder:{reminder.id}:elevated")
                await self._emit_tool("[TOOL] dismiss_reminder", f"Dismissed: {reminder.message}", "info")
                return self._simple_response("Reminder Dismissed", f"Dismissed and silenced: {reminder.message}")

            if name == "clear_stuck_reminders":
                await self._emit_tool("[TOOL] clear_stuck_reminders", "Scanning for stuck reminders...")
                from backend.app.services.reminder_service import ReminderService
                from backend.app.services.watch_service import WatchService
                rs = ReminderService()
                ws = WatchService()
                due = rs.get_due_reminders()
                stuck = [r for r in due if r.recurrence == "once"]
                for r in stuck:
                    rs.complete_reminder(r.id)
                    ws.resolve_alert(f"reminder:{r.id}")
                    ws.resolve_alert(f"reminder:{r.id}:escalated")
                    ws.resolve_alert(f"reminder:{r.id}:elevated")
                msg = f"Cleared {len(stuck)} stuck reminder(s)." if stuck else "No stuck reminders found."
                await self._emit_tool("[TOOL] clear_stuck_reminders", msg, "info")
                return self._simple_response("Reminders Cleared", msg)

            if name == "pause_reminders":
                await self._emit_tool("[TOOL] pause_reminders", "Pausing reminder notifications")
                self._reminders_paused = True
                return self._simple_response("Reminders Paused", "Reminder notifications are paused. Say 'resume reminders' to re-enable.")

            if name == "resume_reminders":
                await self._emit_tool("[TOOL] resume_reminders", "Resuming reminder notifications")
                self._reminders_paused = False
                return self._simple_response("Reminders Resumed", "Reminder notifications are active again.")

            if name == "show_reminder_diagnostics":
                await self._emit_tool("[TOOL] show_reminder_diagnostics", "Running reminder diagnostics...")
                from backend.app.services.reminder_service import ReminderService
                rs = ReminderService()
                active = rs.list_reminders(include_completed=False)
                all_reminders = rs.list_reminders(include_completed=True)
                due = rs.get_due_reminders()
                stuck = [r for r in due if r.recurrence == "once"]
                recurring = [r for r in active if r.recurrence != "once"]
                lines = [
                    "Reminder System Diagnostics",
                    f"Active: {len(active)}",
                    f"Due now: {len(due)}",
                    f"Stuck (one-time, past due): {len(stuck)}",
                    f"Recurring: {len(recurring)}",
                    f"Total (including completed): {len(all_reminders)}",
                    f"Paused: {getattr(self, '_reminders_paused', False)}",
                ]
                if stuck:
                    lines.append("")
                    lines.append("Stuck reminders:")
                    for r in stuck:
                        lines.append(f"  [{r.id}] {r.message} (due: {r.trigger_at})")
                return self._simple_response("Reminder Diagnostics", "\n".join(lines))

            if name == "system_diagnostics":
                await self._emit_tool("[TOOL] system_diagnostics", "Running deep system check...")
                from backend.app.services.system_diagnostics import run_full_diagnostics, format_diagnostics
                results = await run_full_diagnostics()
                text = format_diagnostics(results)
                await self._emit_tool("[TOOL] system_diagnostics", f"Checked {results.get('_summary', {}).get('total_checked', 0)} subsystems", "info")
                return self._simple_response("System Diagnostics", text)

            if name == "add_task":
                title = args.get("title", "").strip()
                project = args.get("project", "").strip()
                await self._emit_tool("[TOOL] add_task", f"Adding task: {title}")
                from backend.app.tools.personal_tool import add_task
                result = add_task(title, project)
                await self._emit_tool("[TOOL] add_task", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response("Task Added" if result["ok"] else "Task Error",
                                               result["summary"], result)

            if name == "list_tasks":
                filter_val = args.get("filter", "pending")
                await self._emit_tool("[TOOL] list_tasks", f"Fetching {filter_val} tasks")
                from backend.app.tools.personal_tool import list_tasks
                result = list_tasks(filter_val)
                await self._emit_tool("[TOOL] list_tasks", result["summary"])
                return self._personal_response("Tasks", self._render_task_list(result), result)

            if name == "complete_task":
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] complete_task", f"Completing task: {query}")
                from backend.app.tools.personal_tool import complete_task
                result = complete_task(query)
                await self._emit_tool("[TOOL] complete_task", result["summary"], "info" if result["ok"] else "warning")
                answer = result["summary"] if result["ok"] else f"Task not found: {query}"
                return self._personal_response("Task Done" if result["ok"] else "Not Found", answer, result)

            if name == "delete_task":
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] delete_task", f"Deleting task: {query}")
                from backend.app.tools.personal_tool import delete_task
                result = delete_task(query)
                await self._emit_tool("[TOOL] delete_task", result["summary"], "info" if result["ok"] else "warning")
                answer = result["summary"] if result["ok"] else f"Task not found: {query}"
                return self._personal_response("Task Deleted" if result["ok"] else "Not Found", answer, result)

            if name == "get_calendar_today":
                await self._emit_tool("[TOOL] get_calendar_today", "Fetching today's events")
                from backend.app.tools.personal_tool import get_calendar_today
                result = get_calendar_today()
                await self._emit_tool("[TOOL] get_calendar_today", result["summary"])
                return self._personal_response("Calendar — Today", self._render_calendar_events(result, "today"), result)

            if name == "get_upcoming_events":
                days = args.get("days", 7)
                await self._emit_tool("[TOOL] get_upcoming_events", f"Fetching next {days} days")
                from backend.app.tools.personal_tool import get_upcoming_events
                result = get_upcoming_events(days)
                await self._emit_tool("[TOOL] get_upcoming_events", result["summary"])
                return self._personal_response(f"Calendar — Next {days} Days",
                                               self._render_calendar_events(result, f"next {days} days"), result)

            if name == "create_calendar_event":
                raw = args.get("raw", "").strip()
                await self._emit_tool("[TOOL] create_calendar_event", f"Creating event: {raw[:60]}")
                from backend.app.tools.personal_tool import create_calendar_event
                result = create_calendar_event(raw)
                await self._emit_tool("[TOOL] create_calendar_event", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response("Event Created" if result["ok"] else "Event Error",
                                               result["summary"], result)

            if name == "delete_calendar_event":
                query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] delete_calendar_event", f"Deleting event: {query}")
                from backend.app.tools.personal_tool import delete_calendar_event
                result = delete_calendar_event(query)
                await self._emit_tool("[TOOL] delete_calendar_event", result["summary"], "info" if result["ok"] else "warning")
                answer = result["summary"] if result["ok"] else f"Event not found: {query}"
                return self._personal_response("Event Deleted" if result["ok"] else "Not Found", answer, result)

            # ── Productivity tools (Phase 12G) ─────────────────────────────────

            if name == "connect_google":
                await self._emit_tool("[TOOL] connect_google", "Generating Google authorization URL")
                from backend.app.tools.productivity_tool import get_google_auth_url
                result = get_google_auth_url()
                if result["ok"]:
                    url = result["data"]["auth_url"]
                    answer = (
                        f"**Connect to Google**\n\n"
                        f"Open this URL in your browser to authorize SILVIA:\n\n"
                        f"`{url}`\n\n"
                        f"After authorizing, Google will redirect back to SILVIA automatically."
                    )
                else:
                    answer = f"Could not generate authorization URL: {result['error']}"
                return self._personal_response("Google Auth", answer, result)

            if name == "show_productivity_status":
                await self._emit_tool("[TOOL] show_productivity_status", "Checking productivity connections")
                from backend.app.tools.productivity_tool import get_productivity_auth_status
                auth = get_productivity_auth_status()
                connected = auth.get("data", {}).get("connected", False) if auth.get("ok") else False
                email = auth.get("data", {}).get("email") if auth.get("ok") else None
                lines = ["**Productivity Status**\n"]
                lines.append(f"Google Connected: {'✓ Yes' if connected else '✗ No'}")
                if email:
                    lines.append(f"Authenticated User: {email}")
                lines.append(f"Gmail: {'✓ Connected' if connected else '✗ Not connected'}")
                lines.append(f"Calendar: {'✓ Connected' if connected else '✗ Not connected'}")
                lines.append("\n**Available Tools:**")
                if connected:
                    lines.append("  • Gmail — read inbox, search, draft, send (with confirmation)")
                    lines.append("  • Google Calendar — view events, create, delete (with confirmation)")
                    lines.append("  • Tasks — local task list")
                    lines.append("  • Reminders — local reminders")
                else:
                    lines.append("  • Tasks — local task list")
                    lines.append("  • Reminders — local reminders")
                    lines.append("  • Gmail / Calendar — say **connect to Google** to enable")
                answer = "\n".join(lines)
                await self._emit_tool("[TOOL] show_productivity_status", "Connected" if connected else "Not connected", "info")
                return self._personal_response("Productivity Status", answer, auth)

            if name == "list_emails":
                folder = args.get("folder", "inbox")
                search = args.get("search", "")
                limit = int(args.get("limit", 10))
                query_display = search if search else "(no filter)"
                await self._emit_tool("[TOOL] list_emails", f"Gmail query: {query_display}")
                from backend.app.tools.productivity_tool import list_emails as _list_emails
                result = _list_emails(folder=folder, search=search, limit=limit)
                await self._emit_tool("[TOOL] list_emails", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response("Gmail", self._render_emails(result), result)

            if name == "search_emails":
                query = args.get("query", "").strip()
                limit = int(args.get("limit", 10))
                await self._emit_tool("[TOOL] search_emails", f"Gmail query: {query}")
                from backend.app.tools.productivity_tool import search_emails as _search_emails
                result = _search_emails(query=query, limit=limit)
                await self._emit_tool("[TOOL] search_emails", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response(f"Gmail — \"{query}\"", self._render_emails(result), result)

            if name == "draft_email":
                to = args.get("to", "").strip()
                subject = args.get("subject", "").strip()
                body = args.get("body", "").strip()
                await self._emit_tool("[TOOL] draft_email", f"Creating draft to {to}")
                from backend.app.tools.productivity_tool import draft_email as _draft_email
                result = _draft_email(to=to, subject=subject, body=body)
                await self._emit_tool("[TOOL] draft_email", result["summary"], "info" if result["ok"] else "error")
                if result["ok"]:
                    d = result["data"]["draft"]
                    answer = (
                        f"Draft saved to Gmail Drafts.\n\n"
                        f"**To:** {d['to']}\n"
                        f"**Subject:** {d['subject'] or '(no subject)'}\n\n"
                        f"{d.get('preview', '')}"
                    )
                else:
                    answer = result["summary"]
                return self._personal_response("Draft Created" if result["ok"] else "Draft Failed", answer, result)

            if name == "send_email":
                to = args.get("to", "").strip()
                subject = args.get("subject", "").strip()
                body = args.get("body", "").strip()
                if not to:
                    return self._simple_response("Send Email", "No recipient specified. Who should I send it to?")
                self._pending_email = {"to": to, "subject": subject, "body": body}
                preview = f"**To:** {to}\n**Subject:** {subject or '(no subject)'}"
                if body:
                    preview += f"\n\n{body[:300]}{'...' if len(body) > 300 else ''}"
                await self._emit_tool("[TOOL] send_email", f"Awaiting confirmation: email to {to}", "warning")
                return self._simple_response(
                    "Confirm Send",
                    f"Ready to send this email:\n\n{preview}\n\nReply **yes** to send, or **cancel** to abort."
                )

            if name == "list_gcal_events":
                date = args.get("date", "today")
                days = int(args.get("days", 1))
                period = "today" if days <= 1 else f"next {days} days"
                await self._emit_tool("[TOOL] list_gcal_events", f"Fetching Google Calendar ({period})")
                from backend.app.tools.productivity_tool import list_gcal_events as _list_gcal
                result = _list_gcal(date=date, days=days)
                await self._emit_tool("[TOOL] list_gcal_events", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response(f"Google Calendar — {period}", self._render_gcal_events(result, period), result)

            if name == "create_gcal_event":
                title = args.get("title", "").strip()
                start_iso = args.get("start_iso", "").strip()
                end_iso = args.get("end_iso", "").strip() or None
                description = args.get("description", "").strip()
                location = args.get("location", "").strip()
                if not title or not start_iso:
                    return self._simple_response("Create Event", "Please provide a title and start time for the event.")
                await self._emit_tool("[TOOL] create_gcal_event", f"Creating event: {title}")
                from backend.app.tools.productivity_tool import create_gcal_event as _create_gcal
                result = _create_gcal(title=title, start_iso=start_iso, end_iso=end_iso, description=description, location=location)
                await self._emit_tool("[TOOL] create_gcal_event", result["summary"], "info" if result["ok"] else "error")
                if result["ok"]:
                    ev = result["data"]["event"]
                    answer = f"Event created: **{ev['title']}** starting {ev.get('start', '')}"
                    if ev.get("link"):
                        answer += f"\n[Open in Google Calendar]({ev['link']})"
                else:
                    answer = result["summary"]
                return self._personal_response("Event Created" if result["ok"] else "Event Failed", answer, result)

            if name == "delete_gcal_event":
                event_id = args.get("event_id", "").strip()
                title = args.get("title", "").strip()
                if not event_id:
                    return self._simple_response("Delete Event", "No event ID specified.")
                self._pending_gcal_delete = {"event_id": event_id, "title": title}
                label = f"**{title}**" if title else f"event `{event_id}`"
                await self._emit_tool("[TOOL] delete_gcal_event", f"Confirmation required: delete {title or event_id}", "warning")
                return self._simple_response(
                    "Confirm Delete",
                    f"Delete {label} from Google Calendar? Reply **yes** to confirm, or **cancel** to abort."
                )

            if name == "semantic_search":
                search_query = args.get("query", "").strip()
                await self._emit_tool("[TOOL] semantic_search", f"Searching memory: {search_query[:60]}")
                from backend.app.tools.memory_tool import semantic_search
                result = await semantic_search(search_query)
                await self._emit_tool("[TOOL] semantic_search", result["summary"])
                return self._personal_response(
                    "Memory Search",
                    self._render_semantic_results(result, search_query),
                    result,
                )

            if name == "list_nodes_by_type":
                node_type = args.get("type", "").strip()
                await self._emit_tool("[TOOL] list_nodes_by_type", f"Listing {node_type} nodes")
                from backend.app.tools.node_tool import list_nodes_by_type
                result = list_nodes_by_type(node_type)
                await self._emit_tool("[TOOL] list_nodes_by_type", result["summary"])
                return self._node_response(
                    f"{node_type.capitalize()} Nodes",
                    self._render_node_list_by_type(result),
                    result,
                )

            if name == "send_node_command":
                node_name = args.get("node", "").strip()
                command = args.get("command", "").strip()
                payload_args = args.get("payload") or {}
                if not node_name or not command:
                    return self._simple_response(
                        "Command",
                        "Which node and command? Try: 'arm drone-01' or 'send drone-01 home'.",
                    )
                _DESTRUCTIVE = {"arm", "disarm", "emergency_stop", "reboot"}
                if command in _DESTRUCTIVE:
                    self._pending_command = {"node": node_name, "command": command, "payload": payload_args}
                    await self._emit_tool(
                        "[TOOL] send_node_command",
                        f"Confirmation required: {command} on {node_name}",
                        "warning",
                    )
                    return self._simple_response(
                        "Confirm Command",
                        f"Send '{command}' to {node_name}? Reply 'yes' to confirm, or 'cancel' to abort.",
                    )
                await self._emit_tool("[TOOL] send_node_command", f"Sending: {command} → {node_name}")
                from backend.app.tools.node_tool import send_node_command as _send_cmd
                result = await _send_cmd(node_name, command, payload_args or None)
                level = "info" if result["ok"] else "error"
                await self._emit_tool("[TOOL] send_node_command", result["summary"], level)
                self._last_tool_ok = result["ok"]
                self._verification.record_result(CapabilityExecutionResult(
                    success=result["ok"], executed=True, source="node_command",
                    raw_output=result.get("summary", ""),
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    node=node_name, capability=command, tool="send_node_command",
                    error=result.get("error", "") if not result["ok"] else "",
                ))
                answer = result["summary"] if result["ok"] else f"Command failed: {result.get('error', 'unknown error')}"
                return self._node_response("Command Sent" if result["ok"] else "Command Failed", answer, result)

            if name == "send_bulk_command":
                node_type = args.get("type", "").strip()
                command = args.get("command", "").strip()
                payload_args = args.get("payload") or {}
                if not node_type or not command:
                    return self._simple_response(
                        "Bulk Command",
                        "Which node type and command? Try: 'land all drones' or 'reboot all vps'.",
                    )
                _DESTRUCTIVE = {"arm", "disarm", "emergency_stop", "reboot"}
                if command in _DESTRUCTIVE:
                    self._pending_command = {"node": f"all {node_type}s", "command": command,
                                             "payload": payload_args, "_bulk_type": node_type}
                    await self._emit_tool(
                        "[TOOL] send_bulk_command",
                        f"Confirmation required: {command} ALL {node_type}s",
                        "warning",
                    )
                    return self._simple_response(
                        "Confirm Bulk Command",
                        f"Send '{command}' to ALL {node_type} nodes? Reply 'yes' to confirm, or 'cancel' to abort.",
                    )
                await self._emit_tool("[TOOL] send_bulk_command", f"Bulk {command} → all {node_type}s")
                from backend.app.tools.node_tool import send_bulk_command as _send_bulk
                result = await _send_bulk(node_type, command, payload_args or None)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] send_bulk_command", result["summary"], level)
                return self._node_response("Bulk Command", self._render_bulk_command_result(result), result)

            if name == "list_services":
                node_name = (args.get("node") or "").strip()
                label = f"on {node_name}" if node_name else "all nodes"
                await self._emit_tool("[TOOL] list_services", f"Listing services {label}")
                from backend.app.services.capability_executor import CapabilityExecutor
                executor = CapabilityExecutor()
                result = await executor.list_node_services(node_name or None)
                await self._emit_tool("[TOOL] list_services", result["summary"])
                return self._node_response(
                    f"Services — {node_name or 'All Nodes'}",
                    self._render_services(result),
                    result,
                )

            if name == "execute_capability":
                capability = args.get("capability", "").strip()
                node_name = (args.get("node") or "").strip()
                cap_args = args.get("args") or {}
                if not capability:
                    return self._simple_response(
                        "Capability",
                        "Specify a capability to execute, e.g. 'play music on nighthawk'.",
                    )
                # Check if this capability requires confirmation (risk = high/critical)
                from backend.app.services.service_registry import ServiceRegistry
                registry = ServiceRegistry()
                matches = registry.find_capability(capability, node_name=node_name or None)
                if matches:
                    first = matches[0]
                    if first.capability_confirmation or first.capability_risk in ("high", "critical"):
                        self._pending_command = {
                            "_capability": capability,
                            "node": node_name,
                            "args": cap_args,
                        }
                        await self._emit_tool(
                            "[TOOL] execute_capability",
                            f"Confirmation required: {capability} on {first.node_name}",
                            "warning",
                        )
                        return self._simple_response(
                            "Confirm Action",
                            f"Execute '{capability}' on {first.node_name}? Reply 'yes' to confirm.",
                        )
                await self._emit_tool("[TOOL] execute_capability", f"{capability} → {node_name or 'auto'}")
                from backend.app.services.capability_executor import CapabilityExecutor
                executor = CapabilityExecutor()
                result = await executor.execute(
                    capability, args=cap_args, node_name=node_name or None,
                    _intent=getattr(self, "_current_intent", ""),
                )
                level = "info" if result["ok"] else "error"
                await self._emit_tool("[TOOL] execute_capability", result["summary"], level)
                self._last_tool_ok = result["ok"]
                self._verification.record_result(CapabilityExecutionResult(
                    success=result["ok"], executed=True,
                    source=result.get("data", {}).get("transport", "capability_executor"),
                    raw_output=result.get("summary", ""),
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    node=node_name or result.get("node", ""),
                    capability=capability, tool="execute_capability",
                    error=result.get("error", "") if not result["ok"] else "",
                ))
                return self._node_response(
                    "Capability" if result["ok"] else "Capability Failed",
                    self._render_capability_result(result),
                    result,
                )

            # ── Fleet management tools (Phase 13B) ────────────────────────────
            if name == "fleet_status":
                await self._emit_tool("[TOOL] fleet_status", "Calculating fleet health…")
                from backend.app.services.fleet_manager import FleetManager
                data = FleetManager().get_fleet_status()
                return self._simple_response("Fleet Status", self._render_fleet_status(data))

            if name == "show_fleet_offline":
                await self._emit_tool("[TOOL] show_fleet_offline", "Checking offline nodes…")
                from backend.app.services.fleet_manager import FleetManager
                nodes = FleetManager().get_offline_nodes()
                return self._simple_response(
                    "Offline Nodes",
                    self._render_fleet_nodes(nodes, "offline"),
                )

            if name == "show_fleet_unhealthy":
                await self._emit_tool("[TOOL] show_fleet_unhealthy", "Checking node health…")
                from backend.app.services.fleet_manager import FleetManager
                nodes = FleetManager().get_unhealthy_nodes()
                return self._simple_response(
                    "Unhealthy Nodes",
                    self._render_fleet_nodes(nodes, "unhealthy"),
                )

            if name == "show_fleet_groups":
                await self._emit_tool("[TOOL] show_fleet_groups", "Grouping nodes…")
                from backend.app.services.fleet_manager import FleetManager
                data = FleetManager().get_fleet_groups()
                return self._simple_response("Node Groups", self._render_fleet_groups(data))

            if name == "fleet_action":
                capability   = args.get("capability", "system.restart").strip()
                filter_type  = args.get("filter_type", "all").strip()
                filter_value = args.get("filter_value", "").strip()
                service_name = args.get("service_name", "").strip()
                action_args  = {"service": service_name} if service_name else {}

                await self._emit_tool("[TOOL] fleet_action", f"{capability} → {filter_type}={filter_value or 'all'}")
                from backend.app.services.fleet_manager import FleetManager
                _intent = getattr(self, "_current_intent", "")
                dry = await FleetManager().execute_fleet_action(
                    capability, filter_type, filter_value, action_args, dry_run=True,
                    _intent=_intent,
                )
                if not dry["target_nodes"]:
                    filter_desc = filter_value or "all nodes"
                    return self._simple_response(
                        "No Targets",
                        f"No nodes found matching {filter_type}={filter_desc}. "
                        "Try 'show node groups' to see available filters.",
                    )

                self._pending_command = {
                    "_fleet_action": {
                        "capability":   capability,
                        "filter_type":  filter_type,
                        "filter_value": filter_value,
                        "args":         action_args,
                    }
                }
                target_list = ", ".join(dry["target_nodes"])
                svc_hint = f" ({service_name})" if service_name else ""
                return self._simple_response(
                    "Fleet Action — Confirm",
                    f"[DRY RUN] Would execute **{capability}{svc_hint}** on "
                    f"**{len(dry['target_nodes'])} node(s)**: {target_list}.\n\n"
                    "Reply **yes** to execute, or anything else to cancel.",
                )

            # ── Brain63 Steward tools (Phase 18B) ─────────────────────────────
            if name == "show_brain63_health":
                await self._emit_tool("[TOOL] show_brain63_health", "checking Brain63 health…")
                from backend.app.services.brain_steward import get_brain_steward
                health = get_brain_steward().get_health()
                return self._simple_response("Brain63 Health", self._render_brain63_health(health))

            if name == "show_brain63_coverage":
                project = args.get("project", "").strip()
                await self._emit_tool("[TOOL] show_brain63_coverage", f"checking coverage{' for ' + project if project else ''}…")
                from backend.app.services.brain_steward import get_brain_steward
                coverage = get_brain_steward().get_coverage(project=project)
                return self._simple_response("Documentation Coverage", self._render_brain63_coverage(coverage))

            if name == "show_brain63_drafts":
                await self._emit_tool("[TOOL] show_brain63_drafts", "fetching drafts…")
                from backend.app.services.brain_steward import get_brain_steward
                drafts = get_brain_steward().get_drafts()
                return self._simple_response("Brain63 Drafts", self._render_brain63_drafts(drafts))

            if name == "brain63_commit":
                await self._emit_tool("[TOOL] brain63_commit", "committing approved draft…")
                from backend.app.services.brain_steward import get_brain_steward
                result = get_brain_steward().commit(args)
                if result.get("ok"):
                    return self._simple_response("Brain63 Committed", f"Committed to `{result.get('file', '')}`.")
                return self._simple_response("Commit Failed", result.get("error", "Unknown error"))

            if name == "update_brain63_roadmap":
                project = args.get("project", "").strip()
                change = args.get("change", "").strip()
                if not project:
                    return self._simple_response("Roadmap Update", "Specify a project. Try: 'update cyberdeck roadmap'")
                await self._emit_tool("[TOOL] update_brain63_roadmap", f"{project}: {change or 'review requested'}")
                from backend.app.services.brain_steward import get_brain_steward, _resolve_file
                bs = get_brain_steward()
                if change:
                    draft = bs.draft_roadmap_update(project, change)
                    session_id = getattr(self, "_current_session_id", "")
                    wf = bs.create_draft_workflow(draft, session_id=session_id)
                    return self._render_workflow_card(wf)
                else:
                    target_file = _resolve_file(project, "roadmap")
                    current = bs._read_file(target_file) if target_file else ""
                    if not current:
                        return self._simple_response("Roadmap", f"No roadmap found for '{project}' in Brain63.")
                    lines = [f"Current roadmap for {project}:", "", current[:1500]]
                    lines.append("\nTo update, say: 'move X to phase Y on " + project + " roadmap'")
                    return self._simple_response("Roadmap", "\n".join(lines))

            # ── Memory Provider tools (Phase 18A) ─────────────────────────────
            if name == "show_memory_providers":
                await self._emit_tool("[TOOL] show_memory_providers", "listing providers…")
                from backend.app.services.memory_manager import get_memory_manager
                providers = get_memory_manager().providers()
                return self._simple_response("Memory Providers", self._render_memory_providers(providers))

            if name == "show_memory_health":
                await self._emit_tool("[TOOL] show_memory_health", "checking health…")
                from backend.app.services.memory_manager import get_memory_manager
                health = get_memory_manager().health()
                return self._simple_response("Memory Health", self._render_memory_health(health))

            if name == "show_memory_timeline":
                project = args.get("project", "").strip()
                label = f" for {project}" if project else ""
                await self._emit_tool("[TOOL] show_memory_timeline", f"building timeline{label}…")
                from backend.app.services.memory_manager import get_memory_manager
                entries = get_memory_manager().timeline(project=project, limit=30)
                return self._simple_response("Memory Timeline", self._render_memory_timeline(entries, project))

            if name == "show_memory_relationships":
                entity = args.get("entity", "").strip()
                await self._emit_tool("[TOOL] show_memory_relationships", f"fetching relationships…")
                from backend.app.services.memory_manager import get_memory_manager
                rels = get_memory_manager().relationships(entity=entity, limit=20)
                return self._simple_response("Relationships", self._render_memory_relationships(rels))

            if name == "unified_memory_search":
                query = args.get("query", "").strip()
                project = args.get("project", "").strip()
                await self._emit_tool("[TOOL] unified_memory_search", f"searching: {query}")
                from backend.app.services.memory_manager import get_memory_manager
                entries = get_memory_manager().search(query=query, project=project, limit=15)
                return self._simple_response("Memory Search", self._render_memory_search(entries, query))

            # ── Workflow tools (Phase 17B) ─────────────────────────────────────
            if name == "list_workflows":
                await self._emit_tool("[TOOL] list_workflows", "fetching workflows…")
                from backend.app.services.workflow_engine import get_workflow_engine
                wfs = get_workflow_engine().get_all(limit=50)
                return self._simple_response("Workflows", self._render_workflow_list(wfs))

            if name == "show_pending_workflows":
                await self._emit_tool("[TOOL] show_pending_workflows", "fetching pending…")
                from backend.app.services.workflow_engine import get_workflow_engine
                wfs = get_workflow_engine().get_pending()
                return self._simple_response("Pending Workflows", self._render_workflow_list(wfs, title="Pending Workflows"))

            if name == "show_workflow_history":
                await self._emit_tool("[TOOL] show_workflow_history", "fetching history…")
                from backend.app.services.workflow_engine import get_workflow_engine
                wfs = get_workflow_engine().get_history(limit=50)
                return self._simple_response("Workflow History", self._render_workflow_list(wfs, title="Workflow History"))

            if name == "get_workflow":
                code = args.get("code", "").strip()
                await self._emit_tool("[TOOL] get_workflow", f"fetching {code}…")
                from backend.app.services.workflow_engine import get_workflow_engine
                wf = get_workflow_engine().get(code)
                if not wf:
                    return self._simple_response("Workflow", f"Workflow '{code}' not found.")
                return self._simple_response("Workflow Detail", self._render_workflow_detail(wf))

            if name == "approve_workflow":
                code = args.get("code", "").strip()
                return await self._handle_workflow_command(f"approve {code}", request)

            if name == "reject_workflow":
                code = args.get("code", "").strip()
                return await self._handle_workflow_command(f"reject {code}", request)

            if name == "cancel_workflow":
                code = args.get("code", "").strip()
                return await self._handle_workflow_command(f"cancel {code}", request)

            if name == "approve_all_workflows":
                max_risk = args.get("max_risk", "")
                suffix = " low risk" if max_risk == "low" else ""
                return await self._handle_workflow_command(f"approve all workflows{suffix}", request)

            if name == "reject_all_workflows":
                return await self._handle_workflow_command("reject all workflows", request)

            # ── Observability tools (Phase 13C) ───────────────────────────────
            if name == "show_recent_actions":
                limit  = int(args.get("limit", 20))
                node   = args.get("node", "").strip() or None
                status = args.get("status", "").strip() or None
                node_desc = f" on {node}" if node else ""
                status_desc = f" [{status}]" if status else ""
                await self._emit_tool("[TOOL] show_recent_actions", f"last {limit}{node_desc}{status_desc}")
                from backend.app.services.execution_ledger import get_ledger
                rows = get_ledger().get_recent(limit=limit, node=node, status=status)
                return self._simple_response("Recent Actions", self._render_execution_log(rows))

            if name == "show_failures":
                limit = int(args.get("limit", 20))
                await self._emit_tool("[TOOL] show_failures", f"last {limit} failures")
                from backend.app.services.execution_ledger import get_ledger
                rows = get_ledger().get_failures(limit=limit)
                return self._simple_response("Failures", self._render_failure_log(rows))

            if name == "show_planner_trace":
                limit = int(args.get("limit", 10))
                await self._emit_tool("[TOOL] show_planner_trace", f"last {limit} decisions")
                from backend.app.services.execution_ledger import get_ledger
                rows = get_ledger().get_planner_trace(limit=limit)
                return self._simple_response("Planner Trace", self._render_planner_trace(rows))

            if name == "show_capability_health":
                await self._emit_tool("[TOOL] show_capability_health", "computing reliability…")
                from backend.app.services.system_health import get_overall_health
                data = get_overall_health()
                return self._simple_response("Capability Health", self._render_capability_health(data))

            if name == "explain_last_action":
                await self._emit_tool("[TOOL] explain_last_action", "looking up last action…")
                from backend.app.services.execution_ledger import get_ledger
                entry = get_ledger().get_last_action()
                if not entry:
                    return self._simple_response(
                        "Last Action",
                        "No actions have been logged yet in this session.",
                    )
                ts        = entry.get("ts", "")[:19].replace("T", " ")
                intent    = entry.get("intent") or "(no intent recorded)"
                cap       = entry.get("capability") or entry.get("tool") or "?"
                node      = entry.get("node") or "local"
                status    = entry.get("status", "?")
                msg       = entry.get("message") or ""
                duration  = entry.get("duration_ms")
                dur_str   = f"  — {duration}ms" if duration is not None else ""
                status_icon = {"success": "●", "failure": "✕", "simulated": "◎",
                               "dry_run": "◌", "partial": "▲"}.get(status, "○")
                lines = [
                    f"{status_icon} **{cap}** on **{node}** — {status.upper()}{dur_str}",
                    f"  Time: {ts}",
                    f"  Triggered by: \"{intent}\"",
                ]
                if msg:
                    lines.append(f"  Result: {msg}")
                return self._simple_response("Last Action Explained", "\n".join(lines))

            # ── Project Intelligence tools (Phase 14A) ──────────────────────
            if name == "project_briefing":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Project Briefing", "Specify a project name, e.g. 'project briefing cyberdeck'.")
                await self._emit_tool("[TOOL] project_briefing", f"Generating intelligence report for {project}…")
                from backend.app.services.project_intelligence import ProjectIntelligence
                data = ProjectIntelligence().get_briefing(project)
                if not data.get("found"):
                    return self._simple_response("Project Not Found", data.get("error", f"No project found matching '{project}'."))
                return self._simple_response(f"Project: {data['project']}", self._render_project_briefing(data))

            if name == "project_blockers":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Project Blockers", "Specify a project name.")
                await self._emit_tool("[TOOL] project_blockers", f"Analysing blockers for {project}…")
                from backend.app.services.project_intelligence import ProjectIntelligence
                blockers = ProjectIntelligence().get_blockers(project)
                return self._simple_response(
                    f"Blockers — {project.title()}",
                    self._render_project_blockers(blockers, project),
                )

            if name == "project_readiness":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Project Readiness", "Specify a project name.")
                await self._emit_tool("[TOOL] project_readiness", f"Checking readiness for {project}…")
                from backend.app.services.project_intelligence import ProjectIntelligence
                data = ProjectIntelligence().get_readiness(project)
                if not data.get("found"):
                    return self._simple_response("Not Found", f"No project found matching '{project}'.")
                pct = data.get("readiness_pct", 0)
                status = data.get("build_status", "unknown")
                missing = data.get("missing", [])
                lines = [f"**{data['project']}** — {pct}% ready  ({status})", ""]
                if missing:
                    lines.append("Missing:")
                    for p in missing[:8]:
                        lines.append(f"  ✕ {p['name']} (need {p['quantity_required']}, have {p.get('available_qty', 0)})")
                else:
                    lines.append("● All required parts available.")
                return self._simple_response("Build Readiness", "\n".join(lines))

            if name == "project_dependencies":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Dependencies", "Specify a project name.")
                await self._emit_tool("[TOOL] project_dependencies", f"Loading dependencies for {project}…")
                from backend.app.services.project_intelligence import ProjectIntelligence
                data = ProjectIntelligence().get_dependencies(project)
                if not data.get("found"):
                    return self._simple_response("Not Found", f"No project found matching '{project}'.")
                lines = [f"**{data['project']}** — {data.get('total', 0)} dependencies", ""]
                hw = data.get("hw_dependencies", [])
                if hw:
                    lines.append("**Hardware parts:**")
                    for d in hw[:10]:
                        icon = "●" if d["status"] == "available" else "✕"
                        lines.append(f"  {icon} {d['name']} ({d['rel']})")
                kg = data.get("kg_dependencies", [])
                if kg:
                    lines.append("")
                    lines.append("**Knowledge graph:**")
                    for d in kg[:8]:
                        lines.append(f"  → {d['name']} [{d['type']}] ({d['rel']})")
                if not hw and not kg:
                    lines.append("No dependencies recorded yet. Add parts via the Hardware Board or link nodes in the knowledge graph.")
                return self._simple_response("Dependencies", "\n".join(lines))

            if name == "projects_using":
                component = args.get("component", "").strip()
                if not component:
                    return self._simple_response("Projects Using", "Specify a component name.")
                await self._emit_tool("[TOOL] projects_using", f"Searching for projects using {component}…")
                from backend.app.services.project_intelligence import ProjectIntelligence
                results = ProjectIntelligence().get_projects_using(component)
                return self._simple_response(
                    f"Projects Using '{component}'",
                    self._render_pi_projects_list(results, f"using '{component}'"),
                )

            if name == "blocked_projects":
                await self._emit_tool("[TOOL] blocked_projects", "Finding blocked projects…")
                from backend.app.services.project_intelligence import ProjectIntelligence
                results = ProjectIntelligence().get_blocked_projects()
                return self._simple_response("Blocked Projects", self._render_pi_projects_list(results, "blocked"))

            if name == "startable_projects":
                await self._emit_tool("[TOOL] startable_projects", "Finding startable projects…")
                from backend.app.services.project_intelligence import ProjectIntelligence
                results = ProjectIntelligence().get_startable_projects()
                if not results:
                    return self._simple_response("Startable Projects", "No projects at >= 80% readiness found. Add parts to the Hardware Board.")
                lines = [f"**{len(results)} project(s) ready to start:**", ""]
                for r in results:
                    lines.append(f"● **{r['name']}** — {r['readiness_pct']}% ready  ({r.get('status', '')} / {r.get('priority', '')})")
                return self._simple_response("Startable Projects", "\n".join(lines))

            if name == "open_board":
                from backend.app.tools.planner import _BOARD_LABELS
                board_id = args.get("board", "command_center")
                route    = args.get("route", "/")
                label    = _BOARD_LABELS.get(board_id, board_id.replace("_", " ").title())
                await self._emit_tool("[TOOL] open_board", f"→ {label} ({route})")
                _PANEL_NOTES = {
                    "fleet":          "The Fleet Dashboard is in the Infrastructure panel on the main Command Center.",
                    "observability":  "Observability is in the Infrastructure panel on the main Command Center.",
                    "infrastructure": "The Infrastructure panel is on the main Command Center.",
                    "mission":        "Mission Control is on the main Command Center.",
                    "desktop":        "Files & Apps is on the main Command Center.",
                    "command_center": "You are already on the Command Center.",
                }
                note    = _PANEL_NOTES.get(board_id, "")
                message = f"Opening **{label}**." + (f" {note}" if note else "")
                return AssistantResponse(
                    mode="conversation",
                    title=f"Navigation: {label}",
                    answer=message,
                    confidence=0.99,
                    reasoning="Internal board navigation.",
                    processing_time_ms=0,
                    sources=[],
                    logs=[CommandLogEntry(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        title=f"Navigation: {label}",
                        detail=message,
                    )],
                    payload={
                        "speech_text": f"Opening {label}.",
                        "internal_navigation": {
                            "board":  board_id,
                            "route":  route,
                            "label":  label,
                        },
                    },
                )

            if name == "show_knowledge_graph":
                project = args.get("project", "").strip()
                await self._emit_tool("[TOOL] show_knowledge_graph", f"{'project: ' + project if project else 'full graph'}…")
                from backend.app.services.knowledge_graph import get_graph, rebuild_from_data_sources
                kg = get_graph()
                summary = kg.get_summary()
                if summary["entity_count"] == 0:
                    rebuild_from_data_sources()
                    summary = kg.get_summary()
                lines = ["**Engineering Knowledge Graph**", ""]
                if summary["entity_count"] == 0:
                    lines.append("The knowledge graph is empty. Add hardware projects, nodes, and tasks to populate it.")
                    lines.append("\nOpen the interactive graph at **/knowledge**")
                else:
                    lines.append(f"Entities: **{summary['entity_count']}**  ·  Relationships: **{summary['relationship_count']}**")
                    lines.append("")
                    type_lines = []
                    for t, c in sorted(summary["type_counts"].items(), key=lambda x: -x[1]):
                        type_lines.append(f"  {t}: {c}")
                    lines.append("By type:\n" + "\n".join(type_lines))
                    if summary["top_connected"]:
                        lines.append("\nMost connected:")
                        for node in summary["top_connected"]:
                            lines.append(f"  ● **{node['name']}** [{node['type']}] — {node['degree']} connections")
                    if project:
                        lines.append(f"\nShowing subgraph for **{project}** on the /knowledge page.")
                    lines.append("\nView the full interactive graph at **/knowledge**")
                return self._simple_response("Knowledge Graph", "\n".join(lines))

            # ── Engineering Memory (Phase 14C) ────────────────────────────────
            if name == "record_project_memory":
                return await self._handle_record_memory(args)

            if name == "get_project_memory":
                return await self._handle_get_memory(args)

            if name == "get_project_timeline":
                return await self._handle_get_timeline(args)

            if name == "search_project_memory":
                return await self._handle_search_memory(args)

            if name == "import_brain63_memory":
                return await self._handle_import_memory(args)

            # ── Service assignment tools (Phase 10B) ──────────────────────────
            if name == "register_node_preset":
                node_name = args.get("node", "").strip()
                preset_name = args.get("preset", "").strip()
                if not node_name or not preset_name:
                    return self._simple_response(
                        "Register Preset",
                        "Specify a node and preset name. Try: 'register nighthawk as NAS' or 'configure pi-zero as media-player'.",
                    )
                await self._emit_tool("[TOOL] register_node_preset", f"{preset_name} → {node_name}")
                from backend.app.tools.service_tool import register_node_preset as _reg_preset
                result = _reg_preset(node_name, preset_name)
                if not result["ok"]:
                    if result.get("error") == "node_not_found":
                        self._pending_command = {
                            "_create_node_for_service": True,
                            "_node_name": node_name,
                            "_then": {"tool": "register_node_preset", "preset": preset_name},
                        }
                        return self._simple_response(
                            "Node Not Found",
                            f"Node '{node_name}' is not in the registry. Would you like me to create it? Reply 'yes' to create it and register as {preset_name}.",
                        )
                    if result.get("error") == "preset_not_found":
                        from backend.app.services.service_presets import SERVICE_PRESETS
                        available = ", ".join(sorted(SERVICE_PRESETS.keys()))
                        return self._simple_response(
                            "Unknown Preset",
                            f"Preset '{preset_name}' not recognised. Available presets: {available}.",
                        )
                    return self._simple_response("Register Failed", result.get("summary", "Failed."))
                level = "info"
                await self._emit_tool("[TOOL] register_node_preset", result["summary"], level)
                # Emit WebSocket event for each added service
                if self.event_service:
                    for svc_name in result.get("added", []):
                        await self.event_service.emit_ws_only({
                            "type": "service_added",
                            "node_name": result["node_name"],
                            "service_name": svc_name,
                        })
                    for svc_name in result.get("updated", []):
                        await self.event_service.emit_ws_only({
                            "type": "service_updated",
                            "node_name": result["node_name"],
                            "service_name": svc_name,
                        })
                return self._simple_response("Services Registered", result["summary"])

            if name == "add_node_service":
                node_name = args.get("node", "").strip()
                service_name = args.get("service", "").strip()
                service_type = args.get("type", "").strip()
                description = args.get("description", "").strip()
                if not node_name or not service_name:
                    return self._simple_response(
                        "Add Service",
                        "Specify a node and service name. Try: 'add samba service to nighthawk'.",
                    )
                await self._emit_tool("[TOOL] add_node_service", f"{service_name} → {node_name}")
                from backend.app.tools.service_tool import add_node_service as _add_svc
                result = _add_svc(node_name, service_name, service_type, description)
                if not result["ok"]:
                    if result.get("error") == "node_not_found":
                        self._pending_command = {
                            "_create_node_for_service": True,
                            "_node_name": node_name,
                            "_then": {"tool": "add_node_service", "service": service_name,
                                      "type": service_type, "description": description},
                        }
                        return self._simple_response(
                            "Node Not Found",
                            f"Node '{node_name}' is not in the registry. Would you like me to create it and add '{service_name}'? Reply 'yes' to proceed.",
                        )
                    return self._simple_response("Add Service Failed", result.get("summary", "Failed."))
                await self._emit_tool("[TOOL] add_node_service", result["summary"], "info")
                if self.event_service:
                    event_type = "service_added" if result.get("action") == "added" else "service_updated"
                    await self.event_service.emit_ws_only({
                        "type": event_type,
                        "node_name": result["node_name"],
                        "service_name": service_name,
                    })
                return self._simple_response(
                    "Service Added" if result.get("action") == "added" else "Service Updated",
                    result["summary"],
                )

            if name == "remove_node_service":
                node_name = args.get("node", "").strip()
                service_name = args.get("service", "").strip()
                if not node_name or not service_name:
                    return self._simple_response(
                        "Remove Service",
                        "Specify a node and service name. Try: 'remove samba service from nighthawk'.",
                    )
                await self._emit_tool("[TOOL] remove_node_service", f"{service_name} from {node_name}")
                from backend.app.tools.service_tool import remove_node_service as _rm_svc
                result = _rm_svc(node_name, service_name)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] remove_node_service", result["summary"], level)
                if result["ok"] and self.event_service:
                    await self.event_service.emit_ws_only({
                        "type": "service_deleted",
                        "node_name": result["node_name"],
                        "service_name": service_name,
                    })
                return self._simple_response(
                    "Service Removed" if result["ok"] else "Service Not Found",
                    result["summary"],
                )

            if name == "rename_node_service":
                node_name = args.get("node", "").strip()
                old_name = args.get("old", "").strip()
                new_name = args.get("new", "").strip()
                if not old_name or not new_name:
                    return self._simple_response(
                        "Rename Service",
                        "Specify old and new names. Try: 'rename service samba to file-sharing on nighthawk'.",
                    )
                if not node_name:
                    return self._simple_response(
                        "Rename Service",
                        f"Which node is '{old_name}' on? Say: 'rename service {old_name} to {new_name} on [node]'.",
                    )
                await self._emit_tool("[TOOL] rename_node_service", f"{old_name} → {new_name} on {node_name}")
                from backend.app.tools.service_tool import rename_node_service as _rename_svc
                result = _rename_svc(node_name, old_name, new_name)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] rename_node_service", result["summary"], level)
                if result["ok"] and self.event_service:
                    await self.event_service.emit_ws_only({
                        "type": "service_updated",
                        "node_name": result["node_name"],
                        "service_name": new_name,
                        "old_name": old_name,
                    })
                return self._simple_response(
                    "Service Renamed" if result["ok"] else "Rename Failed",
                    result["summary"],
                )

            # ── Desktop control (Phase 11) ─────────────────────────────────────

            # ── Phase 11F: URL / modifier / preference ─────────────────────────
            if name == "open_url":
                url = args.get("url", "").strip()
                if not url:
                    return self._simple_response("Open URL", "Which URL or domain should I open?")
                await self._emit_tool("[TOOL] open_url", f"Opening: {url}")
                from backend.app.tools.desktop_tool import open_url as _open_url
                result = _open_url(url)
                await self._emit_tool("[TOOL] open_url", result["summary"], "info" if result["ok"] else "warning")
                return self._simple_response("Browser", result["summary"])

            if name == "open_target":
                target = args.get("target", "").strip()
                modifier = args.get("modifier", "").strip()
                if not target:
                    return self._simple_response("Open", "What would you like to open?")
                label = f"{target} ({modifier})" if modifier else target
                await self._emit_tool("[TOOL] open_target", f"Resolving: {label}")
                from backend.app.tools.desktop_tool import open_target as _open_target
                result = _open_target(target, modifier)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] open_target", result["summary"], level)
                title = "Opened" if result["ok"] else "Not Found"
                return self._simple_response(title, result["summary"])

            if name == "set_launch_preference":
                target = args.get("target", "").strip()
                preferred = args.get("preferred", "").strip()
                if not target or not preferred:
                    return self._simple_response("Preference", "Specify a target and preference, e.g. 'prefer github web'.")
                await self._emit_tool("[TOOL] set_launch_preference", f"{target} → {preferred}")
                from backend.app.tools.desktop_tool import set_launch_preference as _set_pref
                result = _set_pref(target, preferred)
                await self._emit_tool("[TOOL] set_launch_preference", result["summary"], "info")
                return self._simple_response("Preference Saved" if result["ok"] else "Failed", result["summary"])

            if name == "show_launch_target":
                target = args.get("target", "").strip()
                if not target:
                    return self._simple_response("Target Info", "Which target should I show?")
                await self._emit_tool("[TOOL] show_launch_target", f"Target: {target}")
                from backend.app.tools.desktop_tool import show_launch_target as _show_target
                result = _show_target(target)
                await self._emit_tool("[TOOL] show_launch_target", result["summary"][:60], "info")
                return self._simple_response("Launch Target", result["summary"])

            if name == "list_launch_preferences":
                await self._emit_tool("[TOOL] list_launch_preferences", "Fetching preferences")
                from backend.app.tools.desktop_tool import list_launch_preferences as _list_prefs
                result = _list_prefs()
                await self._emit_tool("[TOOL] list_launch_preferences", f"{result['count']} preferences", "info")
                return self._simple_response("Launch Preferences", result["summary"])
            # ── End Phase 11F ──────────────────────────────────────────────────

            if name == "open_location":
                loc_name = args.get("name", "").strip()
                if not loc_name:
                    return self._simple_response("Open Location", "Which folder would you like to open?")
                await self._emit_tool("[TOOL] open_location", f"Opening: {loc_name}")
                from backend.app.tools.desktop_tool import open_location as _open_loc
                result = _open_loc(loc_name)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] open_location", result["summary"], level)
                return self._simple_response(
                    "Location Opened" if result["ok"] else "Location Not Found",
                    result["summary"],
                )

            if name == "find_files":
                query = args.get("query", "").strip()
                extension = args.get("extension", "").strip()
                location = args.get("location", "").strip()
                await self._emit_tool(
                    "[TOOL] find_files",
                    f"Searching: ext={extension or 'any'} query={query or 'any'} loc={location or 'all'}"
                )
                from backend.app.tools.desktop_tool import find_files as _find
                result = _find(query=query, extension=extension, location=location)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] find_files", f"{result.get('count', 0)} results", level)
                return self._simple_response(
                    "File Search",
                    result["summary"],
                )

            if name == "recent_files":
                location = args.get("location", "").strip()
                await self._emit_tool(
                    "[TOOL] recent_files",
                    f"Fetching recent files: loc={location or 'all'}",
                )
                from backend.app.tools.desktop_tool import recent_files as _recent
                result = _recent(location=location)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] recent_files", f"{result.get('count', 0)} results", level)
                return self._simple_response("Recent Files", result["summary"])

            if name == "open_kicad_project":
                project_query = args.get("query", "").strip()
                latest = bool(args.get("latest", False))
                await self._emit_tool(
                    "[TOOL] open_kicad_project",
                    f"Resolving KiCad project: {project_query or 'latest'}",
                )
                from backend.app.tools.desktop_tool import open_kicad_project as _open_kicad_project
                result = _open_kicad_project(query=project_query, latest=latest)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] open_kicad_project", result["summary"], level)
                return self._simple_response(
                    "KiCad Project Opened" if result["ok"] else "KiCad Project Not Opened",
                    result["summary"],
                )

            if name == "open_app":
                app_name = args.get("name", "").strip()
                if not app_name:
                    return self._simple_response("Open App", "Which application would you like to launch?")
                await self._emit_tool("[TOOL] open_app", f"Launching: {app_name}")
                from backend.app.tools.desktop_tool import open_app as _open_app
                result = _open_app(app_name)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] open_app", result["summary"], level)
                return self._simple_response(
                    "App Launched" if result["ok"] else "App Not Found",
                    result["summary"],
                )

            if name == "list_locations":
                await self._emit_tool("[TOOL] list_locations", "Fetching trusted locations")
                from backend.app.tools.desktop_tool import list_locations as _list_locs
                result = _list_locs()
                await self._emit_tool("[TOOL] list_locations", f"{result.get('count', 0)} locations", "info")
                return self._simple_response("Trusted Locations", result["summary"])

            if name == "list_apps":
                await self._emit_tool("[TOOL] list_apps", "Fetching registered apps")
                from backend.app.tools.desktop_tool import list_apps as _list_apps
                result = _list_apps()
                await self._emit_tool("[TOOL] list_apps", f"{result.get('count', 0)} apps", "info")
                return self._simple_response("Applications", result["summary"])

            if name == "scan_apps":
                await self._emit_tool("[TOOL] scan_apps", "Scanning installed applications")
                from backend.app.tools.desktop_tool import scan_apps as _scan_apps
                result = _scan_apps()
                await self._emit_tool("[TOOL] scan_apps", result["summary"], "info")
                return self._simple_response("Application Scan", result["summary"])

            if name == "show_app":
                app_name = args.get("name", "").strip()
                if not app_name:
                    return self._simple_response("Show App", "Which application should I look up?")
                await self._emit_tool("[TOOL] show_app", f"Looking up: {app_name}")
                from backend.app.tools.desktop_tool import show_app as _show_app
                result = _show_app(app_name)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] show_app", result["summary"], level)
                return self._simple_response("Application" if result["ok"] else "Application Not Found", result["summary"])

            if name == "add_location":
                loc_name = args.get("name", "").strip()
                path = args.get("path", "").strip()
                aliases = args.get("aliases", "").strip()
                tags = args.get("tags", "").strip()
                description = args.get("description", "").strip()
                if not loc_name or not path:
                    return self._simple_response(
                        "Add Location",
                        "Specify a name and path: 'add Cyberdeck folder at C:\\...\\Cyberdeck'.",
                    )
                await self._emit_tool("[TOOL] add_location", f"{loc_name} → {path}")
                from backend.app.tools.desktop_tool import add_location as _add_loc
                result = _add_loc(loc_name, path, aliases, tags, description)
                await self._emit_tool("[TOOL] add_location", result["summary"], "info")
                return self._simple_response("Location Added" if result["ok"] else "Failed", result["summary"])

            if name == "add_app":
                app_name = args.get("name", "").strip()
                executable = args.get("executable", "").strip()
                aliases = args.get("aliases", "").strip()
                category = args.get("category", "general").strip()
                description = args.get("description", "").strip()
                if not app_name or not executable:
                    return self._simple_response(
                        "Add App",
                        "Specify a name and executable path: 'add Blender app at C:\\...\\blender.exe'.",
                    )
                await self._emit_tool("[TOOL] add_app", f"{app_name} → {executable}")
                from backend.app.tools.desktop_tool import add_app as _add_app
                result = _add_app(app_name, executable, aliases, category, description)
                await self._emit_tool("[TOOL] add_app", result["summary"], "info")
                return self._simple_response("App Added" if result["ok"] else "Failed", result["summary"])

            # ── Lifecycle (Phase 11D) ──────────────────────────────────────────
            if name == "close_app":
                app_name = args.get("name", "").strip()
                if not app_name:
                    return self._simple_response("Close App", "Which application should I close?")
                await self._emit_tool("[TOOL] close_app", f"Closing: {app_name}")
                from backend.app.tools.desktop_tool import close_app as _close_app
                result = _close_app(app_name)
                level = "info" if result["ok"] else "warning"
                await self._emit_tool("[TOOL] close_app", result["summary"], level)
                return self._simple_response(
                    "App Closed" if result["ok"] else "Close Failed",
                    result["summary"],
                )

            if name == "app_status":
                app_name = args.get("name", "").strip()
                if not app_name:
                    return self._simple_response("App Status", "Which application should I check?")
                await self._emit_tool("[TOOL] app_status", f"Checking: {app_name}")
                from backend.app.tools.desktop_tool import app_status as _app_status
                result = _app_status(app_name)
                await self._emit_tool("[TOOL] app_status", result["summary"], "info")
                return self._simple_response("App Status", result["summary"])

            if name == "list_running_apps":
                await self._emit_tool("[TOOL] list_running_apps", "Checking running applications")
                from backend.app.tools.desktop_tool import list_running_apps as _list_running
                result = _list_running()
                await self._emit_tool("[TOOL] list_running_apps", f"{result.get('count', 0)} running", "info")
                return self._simple_response("Running Applications", result["summary"])

            if name == "show_app_runtime":
                app_name = args.get("name", "").strip()
                if not app_name:
                    return self._simple_response("App Runtime", "Which application should I check?")
                await self._emit_tool("[TOOL] show_app_runtime", f"Runtime state: {app_name}")
                from backend.app.tools.desktop_tool import show_app_runtime as _show_runtime
                result = _show_runtime(app_name)
                await self._emit_tool("[TOOL] show_app_runtime", result["summary"], "info")
                return self._simple_response("App Runtime", result["summary"])

            if name == "schedule_task":
                task_name = args.get("name", "").strip()
                prompt = args.get("prompt", "").strip()
                interval = args.get("interval_minutes", 60)
                if not task_name or not prompt:
                    return self._simple_response(
                        "Schedule Task",
                        "Describe the task and interval: 'schedule task: check node health every 60 minutes'.",
                    )
                await self._emit_tool("[TOOL] schedule_task", f"Creating: {task_name} every {interval}min")
                from backend.app.services.scheduled_task_service import ScheduledTaskService
                svc = ScheduledTaskService()
                task = svc.create_task(task_name, prompt, int(interval))
                await self._emit_tool("[TOOL] schedule_task", f"Scheduled: {task_name}", "info")
                return self._simple_response(
                    "Task Scheduled",
                    f"Scheduled '{task_name}' — runs every {interval} minute{'s' if interval != 1 else ''}, starting in {interval} minute{'s' if interval != 1 else ''}.",
                )

            if name == "list_scheduled_tasks":
                await self._emit_tool("[TOOL] list_scheduled_tasks", "Fetching scheduled tasks")
                from backend.app.services.scheduled_task_service import ScheduledTaskService
                svc = ScheduledTaskService()
                tasks = svc.list_tasks()
                if not tasks:
                    return self._simple_response("Scheduled Tasks", "No scheduled tasks configured.")
                lines = []
                for t in tasks:
                    status = "enabled" if t["enabled"] else "disabled"
                    last = t["last_run"] or "never"
                    lines.append(f"**{t['name']}** — every {t['interval_minutes']}min | {status} | last ran: {last}")
                return self._simple_response("Scheduled Tasks", "\n".join(lines))

            if name == "disable_scheduled_task":
                task_name = args.get("name", "").strip()
                from backend.app.services.scheduled_task_service import ScheduledTaskService
                svc = ScheduledTaskService()
                task = svc.find_by_name(task_name)
                if not task:
                    return self._simple_response("Not Found", f"No scheduled task named '{task_name}'.")
                svc.update_task(task["id"], enabled=0)
                return self._simple_response("Task Disabled", f"Scheduled task '{task['name']}' paused.")

            if name == "delete_scheduled_task":
                task_name = args.get("name", "").strip()
                from backend.app.services.scheduled_task_service import ScheduledTaskService
                svc = ScheduledTaskService()
                task = svc.find_by_name(task_name)
                if not task:
                    return self._simple_response("Not Found", f"No scheduled task named '{task_name}'.")
                svc.delete_task(task["id"])
                return self._simple_response("Task Deleted", f"Scheduled task '{task['name']}' deleted.")

            # ── Hardware Operations (Phase 12A + 12B + 12C) ───────────────────
            if name in {
                "add_component", "list_components", "get_component", "update_component",
                "delete_component", "search_hardware", "hw_inventory_summary",
                "create_hw_project", "list_hw_projects", "get_hw_project",
                "update_hw_project_status", "delete_hw_project",
                "assign_part_to_project", "unassign_part_from_project",
                "list_project_parts", "list_part_projects",
                "add_order", "list_orders", "update_order_status", "delete_order",
                # Phase 12B intelligence
                "build_readiness_check", "show_missing_parts",
                "component_usage_stats", "recommend_orders",
                "show_project_readiness",
                # Phase 12C imports
                "import_bom", "import_inventory", "list_imports",
                "show_imported_components", "show_imported_projects",
                "show_inventory_impact",
            }:
                from backend.app.tools import hardware_tool as _hw
                fn = getattr(_hw, name, None)
                if fn is None:
                    return self._simple_response("Error", f"Hardware tool '{name}' not found.")
                await self._emit_tool(f"[HW] {name}", str(args))
                result = fn(**args)
                level = "info" if result.get("ok") else "error"
                await self._emit_tool(f"[HW] {name}", result.get("summary", ""), level)
                title = "Hardware" if result.get("ok") else "Hardware Error"
                return self._simple_response(title, result.get("summary", "Operation failed."))

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
                inline_username = args.get("username", "").strip()
                if not node_name:
                    self._last_tool_ok = False
                    return self._simple_response(
                        "SSH Failed",
                        "Which node do you want to SSH into? Say 'connect [node name]'.",
                    )
                from backend.app.tools.node_tool import _find_node, _ip_source
                node = _find_node(node_name)
                if not node:
                    self._last_tool_ok = False
                    await self._emit_tool("[TOOL] ssh_node", f"Node not found: {node_name}", "error")
                    return self._simple_response("SSH Failed", f"Node '{node_name}' not found in registry.")
                ip, source = _ip_source(node)
                host = ip or node.hostname or ""
                if not host or host == "local":
                    self._last_tool_ok = False
                    await self._emit_tool("[TOOL] ssh_node", f"No address for {node.name}", "error")
                    return self._simple_response(
                        "SSH Failed",
                        f"No IP or hostname configured for '{node.name}'. Add one with 'update {node_name} IP to ...'.",
                    )
                # Resolve username: inline arg > stored profile > prompt
                username = inline_username or node.ssh_username or ""
                if not username:
                    self._last_tool_ok = False
                    self._pending_ssh = {"node": node.name, "host": host, "source": source}
                    await self._emit_tool("[TOOL] ssh_node", f"Awaiting username for {node.name} ({host})", "info")
                    return self._simple_response(
                        "SSH — Username Required",
                        f"Username for {node.name} ({host})? Reply with your username, or 'cancel' to abort.\n"
                        f"Tip: run 'set ssh username for {node.name} to <username>' to avoid this prompt.",
                    )
                result = await self._execute_ssh_node(node_name, username, source="direct")
                answer = self._format_ssh_result(result)
                return self._node_response("SSH Session" if result["ok"] else "SSH Failed", answer, result)

            if name == "update_ssh_profile":
                node_name = args.get("node", "").strip()
                username = args.get("username", "").strip() or None
                key_path = args.get("key_path", "").strip() or None
                if not node_name:
                    return self._simple_response(
                        "SSH Profile",
                        "Which node? Say 'set ssh username for [node] to [username]'.",
                    )
                await self._emit_tool("[TOOL] update_ssh_profile", f"Updating SSH profile for {node_name}")
                from backend.app.tools.node_tool import update_ssh_profile
                result = update_ssh_profile(node_name, username, key_path)
                await self._emit_tool("[TOOL] update_ssh_profile", result["summary"], "info" if result["ok"] else "error")
                return self._node_response(
                    "SSH Profile Updated" if result["ok"] else "SSH Profile Failed",
                    result["summary"],
                    result,
                )

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
                if result["ok"] and result.get("data"):
                    from backend.app.services.node_service import NodeService as _NS
                    _new_node = _NS().get_node(result["data"]["id"])
                    if _new_node:
                        await self.event_service.emit_ws_only({
                            "type": "node_added",
                            "node": _new_node.model_dump(),
                        })
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

            if name == "merge_nodes":
                source = args.get("source", "").strip()
                target = args.get("target", "").strip()
                if not source or not target:
                    return self._simple_response(
                        "Merge Nodes",
                        "Specify both nodes: 'merge [source] into [target]'. "
                        "The source node will be deleted and its name added as an alias on the target.",
                    )
                await self._emit_tool("[TOOL] merge_nodes", f"Merging '{source}' into '{target}'")
                from backend.app.tools.node_tool import merge_nodes
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, merge_nodes, source, target)
                await self._emit_tool("[TOOL] merge_nodes", result["summary"], "info" if result["ok"] else "error")
                if result["ok"] and result.get("data"):
                    await self.event_service.emit_ws_only({
                        "type": "node_deleted",
                        "node_id": result["data"]["source_id"],
                    })
                answer = result["summary"]
                return self._node_response("Nodes Merged" if result["ok"] else "Merge Failed", answer, result)

            if name == "deduplicate_nodes":
                await self._emit_tool("[TOOL] deduplicate_nodes", "Scanning registry for duplicate nodes")
                from backend.app.tools.node_tool import find_duplicate_nodes
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, find_duplicate_nodes)
                await self._emit_tool("[TOOL] deduplicate_nodes", result["summary"], "info")
                answer = result["summary"]
                if result.get("data", {}).get("count", 0) > 0:
                    answer = result["summary"] + "\n\nTo fix: say 'merge [source] into [target]' for each pair."
                return self._node_response("Deduplication Scan", answer, result)

            # ── System / terminal tools ──────────────────────────────────────
            if name == "get_system_specs":
                await self._emit_tool("[TOOL] get_system_specs", "Reading system hardware via psutil + wmic")
                from backend.app.tools.system_tool import get_system_specs
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, get_system_specs)
                await self._emit_tool("[TOOL] get_system_specs", result["summary"], "info" if result["ok"] else "error")
                self._last_tool_ok = result["ok"]
                self._verification.record_result(CapabilityExecutionResult(
                    success=result["ok"], executed=True, source="local",
                    raw_output=result.get("summary", ""),
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    node="local", capability="system_specs", tool="get_system_specs",
                ))
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
                self._last_tool_ok = result["ok"]
                self._verification.record_result(CapabilityExecutionResult(
                    success=result["ok"], executed=True, source="local",
                    raw_output=result.get("data", {}).get("output", result.get("summary", "")),
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    node="local", capability=f"run_command:{cmd}", tool="run_command",
                    error=result.get("error", "") if not result["ok"] else "",
                ))
                answer, speech = self._render_cmd_output(result)
                source_line = f"\n\n`Source: local execution | Command: {cmd}`"
                return self._system_response(f"$ {cmd[:40]}", answer + source_line, speech, result)

            # ── Mission Control tools ────────────────────────────────────────
            if name == "morning_briefing":
                await self._emit_tool("[TOOL] morning_briefing", "Aggregating operational picture...")
                from backend.app.tools.mission_tool import morning_briefing
                result = morning_briefing()
                await self._emit_tool("[TOOL] morning_briefing", result["summary"], "info" if result["ok"] else "error")
                if not result["ok"]:
                    return self._simple_response("Briefing Unavailable", result["summary"])
                text = self._render_briefing_for_llm(result["data"])
                return await self._synthesize_mission(text, "morning_briefing", result)

            if name == "daily_focus":
                await self._emit_tool("[TOOL] daily_focus", "Computing priority ranking...")
                from backend.app.tools.mission_tool import daily_focus
                result = daily_focus()
                await self._emit_tool("[TOOL] daily_focus", result["summary"], "info" if result["ok"] else "error")
                if not result["ok"]:
                    return self._simple_response("Focus Unavailable", result["summary"])
                text = self._render_focus_for_llm(result["data"])
                return await self._synthesize_mission(text, "daily_focus", result)

            if name == "weekly_review":
                await self._emit_tool("[TOOL] weekly_review", "Compiling weekly summary...")
                from backend.app.tools.mission_tool import weekly_review
                result = weekly_review()
                await self._emit_tool("[TOOL] weekly_review", result["summary"], "info" if result["ok"] else "error")
                if not result["ok"]:
                    return self._simple_response("Weekly Review Unavailable", result["summary"])
                text = self._render_weekly_for_llm(result["data"])
                return await self._synthesize_mission(text, "weekly_review", result)

            if name == "forgotten_items":
                await self._emit_tool("[TOOL] forgotten_items", "Scanning for stale and overdue items...")
                from backend.app.tools.mission_tool import forgotten_items
                result = forgotten_items()
                await self._emit_tool("[TOOL] forgotten_items", result["summary"], "info" if result["ok"] else "error")
                if not result["ok"]:
                    return self._simple_response("Scan Unavailable", result["summary"])
                return self._simple_response("Forgotten Items", self._render_forgotten(result["data"]))

            if name == "evening_review":
                await self._emit_tool("[TOOL] evening_review", "Compiling end-of-day summary...")
                from backend.app.tools.mission_tool import evening_review
                result = evening_review()
                await self._emit_tool("[TOOL] evening_review", result["summary"], "info" if result["ok"] else "error")
                if not result["ok"]:
                    return self._simple_response("Evening Review Unavailable", result["summary"])
                text = self._render_evening_for_llm(result["data"])
                return await self._synthesize_mission(text, "evening_review", result)

            if name == "project_health":
                await self._emit_tool("[TOOL] project_health", "Reading project registry...")
                from backend.app.tools.mission_tool import project_health
                result = project_health()
                await self._emit_tool("[TOOL] project_health", result["summary"], "info" if result["ok"] else "error")
                if not result["ok"]:
                    return self._simple_response("Health Check Unavailable", result["summary"])
                return self._simple_response("Project Health", self._render_project_health(result["data"]["projects"]))

            if name == "list_projects":
                status_filter = args.get("status", "").strip()
                await self._emit_tool("[TOOL] list_projects", f"Fetching{' ' + status_filter if status_filter else ''} projects...")
                from backend.app.tools.mission_tool import list_projects
                result = list_projects(status=status_filter)
                await self._emit_tool("[TOOL] list_projects", result["summary"], "info" if result["ok"] else "error")
                if not result["ok"]:
                    return self._simple_response("Projects Unavailable", result["summary"])
                return self._simple_response("Projects", self._render_projects_list(result["data"]["projects"]))

            if name == "create_project":
                proj_name = args.get("name", "").strip()
                if not proj_name:
                    return self._simple_response("Create Project", "What's the name of the project?")
                await self._emit_tool("[TOOL] create_project", f"Creating project: {proj_name}")
                from backend.app.tools.mission_tool import create_project
                result = create_project(
                    name=proj_name,
                    status=args.get("status", "active"),
                    priority=args.get("priority", "normal"),
                    brain63_key=args.get("brain63_key", ""),
                    notes=args.get("notes", ""),
                )
                await self._emit_tool("[TOOL] create_project", result["summary"], "info" if result["ok"] else "error")
                return self._simple_response("Project Created" if result["ok"] else "Failed", result["summary"])

            if name == "update_project_status":
                proj_name = args.get("name", "").strip()
                new_status = args.get("status", "").strip()
                if not proj_name or not new_status:
                    return self._simple_response("Update Project", "Which project, and what status? Try: 'mark project X as complete'.")
                await self._emit_tool("[TOOL] update_project_status", f"{proj_name} → {new_status}")
                from backend.app.tools.mission_tool import update_project_status
                result = update_project_status(proj_name, new_status)
                await self._emit_tool("[TOOL] update_project_status", result["summary"], "info" if result["ok"] else "warning")
                return self._simple_response("Project Updated" if result["ok"] else "Not Found", result["summary"])

            # ── Workspace Digital Twin tools (Phase 15A) ─────────────────────
            if name == "workspace_status":
                await self._emit_tool("[TWIN] workspace_status", "Building workspace snapshot...")
                from backend.app.services.digital_twin import get_twin
                data = get_twin().workspace_status()
                text = self._render_workspace_status(data)
                await self._emit_tool("[TWIN] workspace_status", "Workspace snapshot complete", "info")
                return self._simple_response("Workspace Status", text)

            if name == "workspace_priorities":
                await self._emit_tool("[TWIN] workspace_priorities", "Computing project rankings...")
                from backend.app.services.digital_twin import get_twin
                priorities = get_twin().priorities()
                text = self._render_workspace_priorities(priorities)
                await self._emit_tool("[TWIN] workspace_priorities", f"{len(priorities)} projects ranked", "info")
                return self._simple_response("Project Rankings", text)

            if name == "daily_briefing":
                await self._emit_tool("[TWIN] daily_briefing", "Building engineering briefing...")
                from backend.app.services.digital_twin import get_twin
                data = get_twin().daily_briefing()
                text = self._render_daily_briefing(data)
                await self._emit_tool("[TWIN] daily_briefing", "Briefing ready", "info")
                return await self._synthesize_mission(text, "daily_briefing", {"ok": True, "data": data})

            if name == "show_blocked_projects":
                await self._emit_tool("[TWIN] show_blocked_projects", "Scanning for blockers...")
                from backend.app.services.digital_twin import get_twin
                blocked = get_twin().blocked_projects()
                text = self._render_blocked_projects(blocked)
                await self._emit_tool("[TWIN] show_blocked_projects", f"{len(blocked)} blocked", "info")
                return self._simple_response("Blocked Projects", text)

            if name == "show_ready_projects":
                await self._emit_tool("[TWIN] show_ready_projects", "Checking readiness...")
                from backend.app.services.digital_twin import get_twin
                ready = get_twin().ready_projects()
                if not ready:
                    return self._simple_response("Ready Projects", "No projects are fully ready to build right now.")
                lines = ["Projects ready to build now:\n"]
                for p in ready:
                    lines.append(f"  {p['name']} — {p['readiness_pct']}% ready [{p['priority']}]")
                    if p.get("recommended_action"):
                        lines.append(f"    → {p['recommended_action']}")
                await self._emit_tool("[TWIN] show_ready_projects", f"{len(ready)} ready", "info")
                return self._simple_response("Ready Projects", "\n".join(lines))

            if name == "what_should_i_work_on":
                await self._emit_tool("[TWIN] what_should_i_work_on", "Analyzing workspace...")
                from backend.app.services.recommendation_engine import get_engine
                result = get_engine().what_should_i_work_on()
                text = self._render_work_recommendation(result)
                # Enrich with screen awareness context
                try:
                    from backend.app.services.workspace_awareness import get_awareness
                    ctx_str = get_awareness().get_context_for_assistant()
                    if ctx_str and "No active context" not in ctx_str:
                        text = f"Current activity: {ctx_str}\n\n{text}"
                except Exception:
                    pass
                await self._emit_tool("[TWIN] what_should_i_work_on", result.get("summary", ""), "info")
                return await self._synthesize_mission(text, "daily_focus", {"ok": True, "data": result})

            if name == "what_to_order":
                await self._emit_tool("[TWIN] what_to_order", "Checking missing parts...")
                from backend.app.services.recommendation_engine import get_engine
                result = get_engine().what_to_order()
                if not result.get("orders"):
                    return self._simple_response("Order Recommendations", result["summary"])
                lines = [result["summary"], ""]
                for o in result["orders"]:
                    lines.append(f"  [{o['priority']}] {o['part']} — for {o['project']}")
                await self._emit_tool("[TWIN] what_to_order", result["summary"], "info")
                return self._simple_response("Order Recommendations", "\n".join(lines))

            if name == "closest_to_completion":
                await self._emit_tool("[TWIN] closest_to_completion", "Analyzing readiness...")
                from backend.app.services.recommendation_engine import get_engine
                result = get_engine().closest_to_completion()
                await self._emit_tool("[TWIN] closest_to_completion", result.get("summary", ""), "info")
                proj = result.get("project")
                if not proj:
                    return self._simple_response("Closest to Completion", result["summary"])
                lines = [result["summary"]]
                if proj.get("blockers"):
                    lines.append(f"  Blockers: {len(proj['blockers'])}")
                if proj.get("missing_parts"):
                    lines.append(f"  Missing: {', '.join(proj['missing_parts'][:3])}")
                return self._simple_response("Closest to Completion", "\n".join(lines))

            if name == "rich_output":
                project = args.get("project", "").strip()
                render_type = args.get("render_type", "").strip()
                await self._emit_tool("[RICH] rich_output", f"Generating {render_type} for {project or 'all'}...")
                from backend.app.services.rich_output_service import render as _rich_render
                result = _rich_render(render_type, project)
                if not result.get("ok") and project and render_type in ("procurement_table", "build_workflow", "checklist"):
                    # Fall back to engineering planner for template-based projects
                    from backend.app.services.engineering_planner import get_planner
                    ep = get_planner()
                    if render_type == "procurement_table":
                        fallback = ep.procurement_plan(project)
                        if fallback.get("ok"):
                            text = self._render_procurement_plan(fallback)
                            return self._simple_response(f"Procurement — {fallback.get('project', project)}", text)
                    elif render_type == "build_workflow":
                        fallback = ep.generate_roadmap(project)
                        if fallback.get("ok"):
                            text = self._render_planner_roadmap(fallback)
                            return self._simple_response(f"Roadmap — {fallback.get('project', project)}", text)
                    elif render_type == "checklist":
                        fallback = ep.generate_roadmap(project)
                        if fallback.get("ok"):
                            text = self._render_planner_roadmap(fallback)
                            return self._simple_response(f"Roadmap — {fallback.get('project', project)}", text)
                if not result.get("ok"):
                    return self._simple_response("Rich Output", result.get("markdown", "No data available."))
                await self._emit_tool("[RICH] rich_output", f"Rendered {render_type}", "info")
                payload = result.get("payload", {})
                payload["speech_text"] = f"Here's the {render_type.replace('_', ' ')} for {project or 'all projects'}."
                return AssistantResponse(
                    mode="conversation",
                    answer=result["markdown"],
                    title=payload.get("rich_output", {}).get("title", "Rich Output"),
                    processing_time_ms=0,
                    payload=payload,
                )

            if name == "reconcile_project_orders":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Order Recommendations", "Which project? Try: 'what should I order next for Cyberdeck'")
                await self._emit_tool("[TWIN] reconcile_project_orders", f"Reconciling {project}...")
                from backend.app.services.project_reconciler import get_reconciler
                result = get_reconciler().reconcile_project(project)
                if not result.get("found"):
                    return self._simple_response("Not Found", result.get("error", f"Project '{project}' not found."))
                text = self._render_reconciled_orders(result)
                await self._emit_tool("[TWIN] reconcile_project_orders", result.get("summary", ""), "info")
                return self._simple_response(f"Order Status — {result['project']}", text)

            if name == "mark_item_acquired":
                project = args.get("project", "").strip()
                items_raw = args.get("items", "").strip()
                state = args.get("state", "owned").strip()
                if not project or not items_raw:
                    return self._simple_response("Update Items", "Which items and project? Try: 'I already bought the screen for Cyberdeck'")
                item_names = [i.strip() for i in re.split(r",\s*|\s+and\s+", items_raw) if i.strip()]
                item_names = [re.sub(r"^(?:the|a|an)\s+", "", i, flags=re.I) for i in item_names]
                await self._emit_tool("[TWIN] mark_item_acquired", f"Updating {len(item_names)} item(s) for {project}...")
                from backend.app.services.project_reconciler import get_reconciler
                result = get_reconciler().mark_acquired(project, item_names, state=state)
                if not result.get("ok"):
                    return self._simple_response("Update Failed", result.get("error", "Could not update."))
                await self._emit_tool("[TWIN] mark_item_acquired", result.get("summary", ""), "info")
                return self._simple_response("Items Updated", result["summary"])

            # ── Screen Awareness tools (Phase 16A) ─────────────────────────
            if name == "show_workspace_context":
                await self._emit_tool("[SCREEN] workspace_context", "Detecting current context...")
                from backend.app.services.workspace_awareness import get_awareness
                ctx = get_awareness().get_context()
                text = self._render_workspace_context(ctx)
                await self._emit_tool("[SCREEN] workspace_context", ctx.get("session_type", ""), "info")
                return self._simple_response("Workspace Context", text)

            if name == "show_active_project":
                await self._emit_tool("[SCREEN] active_project", "Detecting active project...")
                from backend.app.services.workspace_awareness import get_awareness
                proj = get_awareness().get_active_project()
                if proj.get("project"):
                    text = f"Active project: {proj['project']}"
                    if proj.get("app"):
                        text += f"\nDetected from: {proj['app']}"
                    if proj.get("file"):
                        text += f"\nCurrent file: {proj['file']}"
                    if proj.get("registry_match"):
                        text += f"\nRegistry match: {proj['registry_match']}"
                else:
                    text = "No active project detected. Try opening a project in VS Code or an engineering tool."
                await self._emit_tool("[SCREEN] active_project", proj.get("project", "none"), "info")
                return self._simple_response("Active Project", text)

            if name == "show_active_file":
                await self._emit_tool("[SCREEN] active_file", "Detecting active file...")
                from backend.app.services.workspace_awareness import get_awareness
                f = get_awareness().get_active_file()
                if f.get("file"):
                    text = f"Active file: {f['file']}"
                    if f.get("language"):
                        text += f"\nLanguage: {f['language']}"
                    if f.get("project"):
                        text += f"\nProject: {f['project']}"
                    if f.get("app"):
                        text += f"\nApplication: {f['app']}"
                else:
                    text = "No active file detected."
                await self._emit_tool("[SCREEN] active_file", f.get("file", "none"), "info")
                return self._simple_response("Active File", text)

            if name == "show_active_application":
                await self._emit_tool("[SCREEN] active_app", "Detecting active application...")
                from backend.app.services.workspace_awareness import get_awareness
                app = get_awareness().get_active_application()
                text = f"Active application: {app.get('app', 'Unknown')}"
                if app.get("title"):
                    text += f"\nWindow: {app['title'][:80]}"
                if app.get("category"):
                    text += f"\nCategory: {app['category']}"
                if app.get("tool_type"):
                    text += f"\nType: {app['tool_type']}"
                await self._emit_tool("[SCREEN] active_app", app.get("app", ""), "info")
                return self._simple_response("Active Application", text)

            # ── Session Continuity tools (Phase 16B) ──────────────────────
            if name == "show_recent_sessions":
                await self._emit_tool("[SESSION] recent_sessions", "Loading session history...")
                from backend.app.services.session_manager import get_session_manager
                sm = get_session_manager()
                sm.build_sessions_from_log()
                sessions = sm.get_recent_sessions(hours=48, limit=15)
                text = self._render_sessions(sessions)
                await self._emit_tool("[SESSION] recent_sessions", f"{len(sessions)} session(s)", "info")
                return self._simple_response("Recent Sessions", text)

            if name == "show_last_session":
                project = args.get("project", "").strip() or None
                await self._emit_tool("[SESSION] last_session", "Finding last session...")
                from backend.app.services.session_manager import get_session_manager
                sm = get_session_manager()
                sm.build_sessions_from_log()
                last = sm.get_last_session(project)
                if not last:
                    # Fall back to context awareness
                    from backend.app.services.workspace_awareness import get_awareness
                    recent = get_awareness().get_recent_projects(hours=24)
                    if recent:
                        lines = ["Recent project activity (from context log):", ""]
                        for r in recent:
                            lines.append(f"  {r['project']} — {r['entries']} check(s) via {r.get('apps', 'unknown')}")
                        return self._simple_response("Recent Activity", "\n".join(lines))
                    return self._simple_response("Last Session", "No previous sessions recorded. Work in an engineering tool to build session history.")
                text = self._render_single_session(last)
                await self._emit_tool("[SESSION] last_session", last.get("project", ""), "info")
                return self._simple_response("Last Session", text)

            if name == "continue_project":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Continue Project", "Which project? Try: 'continue cyberdeck'")
                await self._emit_tool("[SESSION] continue_project", f"Preparing continuity for {project}...")
                from backend.app.services.session_manager import get_session_manager
                result = get_session_manager().continue_project(project)
                if not result.get("ok"):
                    return self._simple_response("Continue Project", result.get("error", f"Could not find project '{project}'."))
                text = self._render_continue_project(result)
                await self._emit_tool("[SESSION] continue_project", result.get("summary", ""), "info")
                return self._simple_response(f"Continue — {result['project']}", text)

            if name == "restore_workspace":
                project = args.get("project", "").strip()
                await self._emit_tool("[SESSION] restore_workspace", f"Restoring workspace{' for ' + project if project else ''}...")
                from backend.app.services.workspace_restore import get_restore
                if not project:
                    result = get_restore().restore_last_session()
                else:
                    result = get_restore().restore(project)
                if not result.get("ok"):
                    return self._simple_response("Workspace Restore", result.get("error", "Could not restore workspace."))
                await self._emit_tool("[SESSION] restore_workspace", result.get("summary", ""), "info")
                return self._simple_response(f"Workspace Restored — {result.get('project', '')}", result["summary"])

            if name == "show_accomplishments":
                hours = int(args.get("hours", 24))
                await self._emit_tool("[SESSION] accomplishments", f"Reviewing last {hours}h...")
                from backend.app.services.session_manager import get_session_manager
                sm = get_session_manager()
                sm.build_sessions_from_log()
                result = sm.get_accomplishments(hours=hours)
                text = self._render_accomplishments(result)
                await self._emit_tool("[SESSION] accomplishments", result.get("summary", ""), "info")
                return self._simple_response("Accomplishments", text)

            # ── Engineering Planner tools (Phase 15B) ──────────────────────
            if name == "plan_project":
                desc = args.get("description", "").strip()
                if not desc:
                    return self._simple_response("Project Planner", "What would you like to build? Try: 'plan a GPS tracker'")
                await self._emit_tool("[PLANNER] plan_project", f"Designing: {desc}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().design_project(desc)
                text = self._render_project_design(result)
                await self._emit_tool("[PLANNER] plan_project", result.get("summary", ""), "info")
                return self._simple_response(f"Project Design — {result.get('project_name', desc)}", text)

            if name == "generate_bom":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("BOM Generator", "Which project? Try: 'generate BOM for rover'")
                await self._emit_tool("[PLANNER] generate_bom", f"Generating BOM for {project}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().generate_bom(project)
                if not result.get("ok"):
                    return self._simple_response("BOM Generator", result.get("error", "Could not generate BOM."))
                text = self._render_bom(result)
                await self._emit_tool("[PLANNER] generate_bom", result.get("summary", ""), "info")
                payload = {"rich_output": self._bom_rich_payload(result)}
                payload["speech_text"] = f"BOM for {result['project']}: {result['total']} components, {result['available']} available."
                return AssistantResponse(mode="conversation", answer=text,
                    title=f"BOM — {result['project']}", processing_time_ms=0, payload=payload)

            if name == "generate_roadmap_plan":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Roadmap Generator", "Which project? Try: 'generate roadmap for rover'")
                await self._emit_tool("[PLANNER] generate_roadmap", f"Generating roadmap for {project}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().generate_roadmap(project)
                if not result.get("ok"):
                    return self._simple_response("Roadmap Generator", result.get("error", "Could not generate roadmap."))
                text = self._render_planner_roadmap(result)
                await self._emit_tool("[PLANNER] generate_roadmap", result.get("summary", ""), "info")
                payload = {"rich_output": self._roadmap_rich_payload(result)}
                payload["speech_text"] = f"Roadmap for {result['project']}: {result['total_phases']} phases."
                return AssistantResponse(mode="conversation", answer=text,
                    title=f"Roadmap — {result['project']}", processing_time_ms=0, payload=payload)

            if name == "planner_gap_analysis":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Gap Analysis", "Which project? Try: 'what am I missing for rover'")
                await self._emit_tool("[PLANNER] gap_analysis", f"Analyzing gaps for {project}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().gap_analysis(project)
                if not result.get("ok"):
                    return self._simple_response("Gap Analysis", result.get("error", "Could not analyze."))
                text = self._render_gap_analysis(result)
                await self._emit_tool("[PLANNER] gap_analysis", result.get("summary", ""), "info")
                return self._simple_response(f"Gap Analysis — {result['project']}", text)

            if name == "planner_can_i_build":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Buildability Check", "Which project? Try: 'can I build a rover'")
                await self._emit_tool("[PLANNER] can_i_build", f"Checking buildability: {project}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().can_i_build(project)
                if not result.get("ok"):
                    return self._simple_response("Buildability Check", result.get("error", "Could not check."))
                await self._emit_tool("[PLANNER] can_i_build", result.get("summary", ""), "info")
                return self._simple_response(f"Can I Build — {result['project']}", result["summary"])

            if name == "planner_what_can_i_build":
                await self._emit_tool("[PLANNER] what_can_i_build", "Scanning inventory for project ideas...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().what_can_i_build()
                text = self._render_what_can_i_build(result)
                await self._emit_tool("[PLANNER] what_can_i_build", result.get("summary", ""), "info")
                return self._simple_response("What Can I Build", text)

            if name == "planner_architecture":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Architecture", "Which project? Try: 'architecture for rover'")
                await self._emit_tool("[PLANNER] architecture", f"Getting architecture for {project}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().get_architecture(project)
                if not result.get("ok"):
                    return self._simple_response("Architecture", result.get("error", "No architecture data."))
                text = self._render_architecture(result)
                await self._emit_tool("[PLANNER] architecture", result.get("summary", ""), "info")
                return self._simple_response(f"Architecture — {result.get('project', project)}", text)

            if name == "planner_procurement":
                project = args.get("project", "").strip()
                if not project:
                    return self._simple_response("Procurement Plan", "Which project? Try: 'procurement plan for rover'")
                await self._emit_tool("[PLANNER] procurement", f"Generating procurement plan for {project}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().procurement_plan(project)
                if not result.get("ok"):
                    return self._simple_response("Procurement Plan", result.get("error", "Could not generate plan."))
                text = self._render_procurement_plan(result)
                await self._emit_tool("[PLANNER] procurement", result.get("summary", ""), "info")
                return self._simple_response(f"Procurement — {result.get('project', project)}", text)

            if name == "planner_create_project":
                proj_name = args.get("name", "").strip()
                tmpl_id = args.get("template_id", "").strip() or None
                if not proj_name:
                    return self._simple_response("Create Project", "What's the project name? Try: 'create project rover'")
                await self._emit_tool("[PLANNER] create_project", f"Creating project: {proj_name}...")
                from backend.app.services.engineering_planner import get_planner
                result = get_planner().create_project(proj_name, template_id=tmpl_id)
                if not result.get("ok"):
                    return self._simple_response("Create Project", result.get("error", "Could not create project."))
                await self._emit_tool("[PLANNER] create_project", result.get("summary", ""), "info")
                return self._simple_response("Project Created", result["summary"])

            if name == "list_project_templates":
                await self._emit_tool("[PLANNER] list_templates", "Loading templates...")
                from backend.app.services.engineering_planner import get_planner
                templates = get_planner().list_templates()
                text = self._render_templates(templates)
                await self._emit_tool("[PLANNER] list_templates", f"{len(templates)} templates", "info")
                return self._simple_response("Project Templates", text)

        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            logger.warning("Tool '%s' failed with args %s: %s", name, args, exc)
            await self._emit_tool(f"[TOOL] {name}", err, "error")

        return None

    async def _generate_capability_response(
        self, query: str, request: AssistantRequest
    ) -> AssistantResponse:
        """LLM response grounded in the capability map — for self-assessment queries.

        Uses _CONV_BASE + GOAL_PROMPTS["capability"] (which embeds the actual capability
        block) + few-shot examples. Temperature is lower than social chat to keep answers
        factual. Returns a deterministic fallback if the LLM is unavailable.
        """
        from backend.app.services.persona import (
            _CONV_BASE, _CONV_EXAMPLES, GOAL_PROMPTS, CURIOSITY_OFF,
        )

        system = _CONV_BASE
        if "capability" in GOAL_PROMPTS:
            system += "\n\n" + GOAL_PROMPTS["capability"]
        system += "\n\n" + CURIOSITY_OFF

        history: list[dict] = []
        if self.memory_service:
            history = self.memory_service.get_ollama_messages(request.session_id, limit=4)

        messages = [{"role": "system", "content": system}]
        messages.extend(_CONV_EXAMPLES.get("capability", []))
        messages.extend(history[-4:])
        messages.append({"role": "user", "content": query})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 400, "temperature": 0.35, "num_ctx": 4096},
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(OLLAMA_CHAT_URL, json=payload)
                resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "").strip()
            if content:
                await self._emit_tool("[CAPABILITY]", "Self-assessment query answered from capability map", "info")
                return self._simple_response("SILVIA Capabilities", content)
        except Exception as exc:
            logger.warning("Capability response failed: %s", exc)

        return self._simple_response(
            "SILVIA Capabilities",
            "Available: Time, Weather (if configured), Web Search (if configured), Stock Prices, "
            "Node Registry, Reminders, Tasks, Calendar (local only), Memory, Scheduled Tasks, Hermes, Voice. "
            "Partial: Node Monitoring, Node Control, Watch Officer, Proactive Notifications, World Intelligence. "
            "Not implemented: Email, Browser Automation, External Integrations (GitHub, Slack, etc.).",
        )

    def _get_entity_correction(self, entity: str) -> str | None:
        """Check memory for a user correction stored for this entity."""
        if not self.memory_service:
            return None
        key = f"correction_{re.sub(r'[^a-z0-9]', '_', entity.lower())}"
        return self.memory_service.recall(key)

    def _brain63_entity_answer(self, entity: str, query_type: str):
        """Query Brain63 for entity content. Returns Brain63Answer or None."""
        if not self.brain63_service:
            return None
        try:
            chunks = self.brain63_service.search(
                query=entity, entity_hint=entity, query_type=query_type, top_k=6
            )
            if not chunks:
                return None
            if query_type == "status":
                return self.brain63_service.answer_status(entity, chunks)
            elif query_type == "overview":
                return self.brain63_service.answer_overview(entity, chunks)
            elif query_type == "decisions":
                return self.brain63_service.answer_decisions(entity, chunks)
            else:
                return self.brain63_service.answer_general(entity, chunks)
        except Exception as exc:
            logger.warning("Brain63 lookup failed for entity=%r: %s", entity, exc)
            return None

    def _node_context_block(self, query: str) -> str:
        """
        Build a compact NODE REGISTRY block for LLM injection.

        Triggers when the query mentions a registered node name/ID, or asks about
        "my devices / nodes / machines". Always reads live from NodeService so the
        LLM never has to guess at IP addresses, statuses, or roles.

        Returns "" when no relevant nodes are found.
        """
        from backend.app.services.node_service import NodeService
        import json as _json
        try:
            svc = NodeService()
            nodes = svc.list_nodes()
        except Exception:
            return ""
        if not nodes:
            return ""

        lowered = query.lower()

        _FLEET_TRIGGERS = (
            "my devices", "my nodes", "my machines", "all nodes", "all devices",
            "the fleet", "list nodes", "what nodes", "which nodes",
        )
        inject_all = any(t in lowered for t in _FLEET_TRIGGERS)

        matched = []
        if not inject_all:
            for node in nodes:
                identifiers = [node.id.lower(), node.name.lower()]
                if node.hostname and node.hostname != "local":
                    identifiers.append(node.hostname.lower())
                if node.tailscale_ip:
                    identifiers.append(node.tailscale_ip.lower())
                if any(ident in lowered for ident in identifiers):
                    matched.append(node)

        if not matched and not inject_all:
            return ""

        targets = nodes if inject_all else matched

        lines = [
            "NODE REGISTRY — live infrastructure state.",
            "Use this to answer device-specific questions. Do not invent IPs, roles, or specs not shown here.\n",
        ]
        for node in targets:
            try:
                tags = _json.loads(node.tags) if isinstance(node.tags, str) else (node.tags or [])
            except Exception:
                tags = []
            parts = [f"{node.name.upper()} ({node.id})"]
            parts.append(f"type={node.type}")
            parts.append(f"status={node.status}")
            if node.tailscale_ip:
                parts.append(f"tailscale={node.tailscale_ip}")
            elif node.hostname and node.hostname != "local":
                parts.append(f"ip={node.hostname}")
            parts.append(f"agent={'yes' if node.agent_url else 'no'}")
            if tags:
                parts.append(f"tags=[{', '.join(tags)}]")
            if node.notes:
                parts.append(f"notes={node.notes[:100]}")
            lines.append("  " + " | ".join(parts))

        return "\n".join(lines)

    def _brain63_context_block(self, query: str) -> str:
        """
        Scan query for entity mentions, fetch Brain63 facts, return a compact
        context block for injection into the LLM system prompt.

        This grounds ALL conversational paths — not just explicit status queries.
        When the user mentions a project, the LLM receives the actual Brain63 facts
        and an instruction not to add anything beyond them.

        Returns "" when Brain63 is unavailable or no entities are mentioned.
        """
        if not self.brain63_service:
            return ""
        raw_mentions = {
            m.group(0).lower().replace(" ", "").replace("-", "")
            for m in _ENTITY_DETECT_RE.finditer(query)
        }
        if not raw_mentions:
            return ""

        from backend.app.services.brain63_service import _first_sentence_or_line

        lines: list[str] = [
            "BRAIN63 FACTS — your only source for project details below.",
            "Cite the filename in brackets. State nothing about these projects beyond what is listed.",
            "For any detail not shown: say \"Brain63 has no record of that.\"\n",
        ]
        found_any = False

        for raw_entity in sorted(raw_mentions):
            label = raw_entity.upper()
            try:
                status_chunks = self.brain63_service.search(
                    query=raw_entity, entity_hint=raw_entity, query_type="status", top_k=3
                )
                overview_chunks = self.brain63_service.search(
                    query=raw_entity, entity_hint=raw_entity, query_type="overview", top_k=2
                )
                # Merge, dedup by object identity via file_path
                seen: set[str] = set()
                merged = []
                for c in status_chunks + overview_chunks:
                    if c.file_path not in seen:
                        seen.add(c.file_path)
                        merged.append(c)

                if not merged:
                    lines.append(f"{label}: No Brain63 notes found.")
                    continue

                found_any = True
                for chunk in merged[:3]:
                    fname = chunk.file_path.split("/")[-1]
                    # Extract most informative single line
                    if chunk.note_type == "status":
                        fact = ""
                        for ln in chunk.content.split("\n"):
                            ll = ln.lower().strip()
                            if any(ll.startswith(p) for p in ("current phase", "phase:", "phase ")):
                                fact = ln.strip()
                                break
                        if not fact:
                            fact = _first_sentence_or_line(chunk.content)
                    else:
                        fact = _first_sentence_or_line(chunk.content)

                    # Skip wiki-link-only lines, table rows, empty
                    if (
                        not fact
                        or fact.startswith("|")
                        or fact.startswith("[[")
                        or (fact.startswith("- ") and "[[" in fact)
                    ):
                        continue

                    lines.append(f"{label} [{fname}]: {fact[:200]}")

            except Exception as exc:
                logger.debug("Brain63 context block for %r: %s", raw_entity, exc)

        if not found_any:
            return ""
        return "\n".join(lines)

    def _handle_entity_query(self, raw: str) -> AssistantResponse | None:
        """Route device/project queries to Brain63 (primary) or registry (fallback).

        Brain63 is the authoritative knowledge source for all projects and devices.
        The static registry is used only when Brain63 has no relevant content.
        Runs before the social engine so entity queries never reach the raw LLM.
        """
        from backend.app.services.device_registry import get_device, describe_device, describe_sensors
        from backend.app.services.project_registry import find_project, describe_project

        def _first_group(m: re.Match) -> str | None:
            return next((g for g in m.groups() if g), None)

        # Device hardware/sensor queries — registry is authoritative (confirmed hardware facts)
        m = _DEVICE_PROP_RE.search(raw)
        if m:
            entity = _first_group(m)
            if entity and get_device(entity.lower()):
                correction = self._get_entity_correction(entity)
                answer = describe_sensors(entity, correction)
                return self._simple_response("Device Registry", answer)

        # Brain63 decision queries — "what did I decide about X"
        m = _DECISION_QUERY_RE.search(raw)
        if m:
            entity = _first_group(m) or ""
            b63_answer = self._brain63_entity_answer(entity, "decisions")
            if b63_answer:
                return self._grounded_brain63_response("Brain63", b63_answer)
            return self._simple_response(
                "Brain63",
                f"No decision records found in Brain63 for '{entity}'.",
            )

        # Brain63 roadmap/vision queries — "what's the plan for X"
        m = _ROADMAP_QUERY_RE.search(raw)
        if m:
            entity = _first_group(m) or ""
            b63_answer = self._brain63_entity_answer(entity, "roadmap")
            if b63_answer:
                return self._grounded_brain63_response("Brain63", b63_answer)
            return None  # Let LLM path handle if Brain63 has nothing

        # Project status/progress — Brain63 primary, registry fallback
        m = _PROJECT_STATUS_RE.search(raw)
        if m:
            entity = _first_group(m)
            if entity:
                correction = self._get_entity_correction(entity)
                if correction:
                    return self._simple_response("Project Status", f"{entity}: {correction}")
                b63_answer = self._brain63_entity_answer(entity, "status")
                if b63_answer:
                    return self._grounded_brain63_response("Brain63", b63_answer)
                answer = describe_project(entity, None)
                return self._simple_response("Project Registry", answer)

        # General entity info — Brain63 overview primary, registry fallback
        m = _ENTITY_INFO_RE.search(raw)
        if m:
            entity = _first_group(m)
            if entity:
                correction = self._get_entity_correction(entity)
                if correction:
                    return self._simple_response("Entity Info", f"{entity}: {correction}")
                b63_answer = self._brain63_entity_answer(entity, "overview")
                if b63_answer:
                    return self._grounded_brain63_response("Brain63", b63_answer)
                # Static registry fallback
                if get_device(entity.lower()):
                    answer = describe_device(entity, None)
                elif find_project(entity.lower()):
                    answer = describe_project(entity, None)
                else:
                    return None
                return self._simple_response("Entity Info", answer)

        return None

    # ── Presence Mode (Phase 16C) ───────────────────────────────────────────
    _WORK_ON_RE = re.compile(
        r"^(?:let'?s?\s+)?(?:work\s+on|focus\s+on|switch\s+to|working\s+on|set\s+focus\s+to)\s+(?:the\s+)?(?P<project>.+?)(?:\s+today)?[\.\?!]?$",
        re.I,
    )
    _SET_ACTIVE_RE = re.compile(
        r"^set\s+(?P<project>.+?)\s+as\s+active(?:\s+(?P<rest>.*))?[\.\?!]?$",
        re.I,
    )
    _WORK_SESSION_START_RE = re.compile(
        r"^(?:start\s+(?:a\s+)?work\s+session|begin\s+(?:work\s+)?session)(?:\s+(?:on|for)\s+(?P<project>.+?))?[\.\?!]?$",
        re.I,
    )
    _COMPOUND_ACTION_RE = re.compile(
        r"^(?P<target>.+?)\s*(?:,\s*(?:and\s+)?|\s+and\s+)"
        r"(?P<action>(?:open|launch|start|run|ssh|connect|show|close|navigate)\s+.+)$",
        re.I,
    )
    _WORK_SESSION_END_RE = re.compile(
        r"^(?:end\s+(?:work\s+)?session|stop\s+(?:work\s+)?session|wrap\s+up\s+session|session\s+done)[\.\?!]?$",
        re.I,
    )
    _FOCUS_ON_RE = re.compile(r"^focus\s+mode\s+on[\.\?!]?$", re.I)
    _FOCUS_OFF_RE = re.compile(r"^focus\s+mode\s+off[\.\?!]?$", re.I)
    _PRESENCE_STATUS_RE = re.compile(
        r"^(?:show\s+)?(?:presence|conversation)\s+(?:status|context)[\.\?!]?$", re.I,
    )
    _RESET_CONTEXT_RE = re.compile(
        r"^reset\s+(?:conversation\s+)?context[\.\?!]?$", re.I,
    )

    async def _handle_presence_command(self, raw: str, presence, request) -> "AssistantResponse | None":
        m = self._WORK_ON_RE.match(raw)
        if m:
            project_raw = m.group("project").strip()

            # Split compound intents: "nighthawk, open the ssh terminal"
            compound = self._COMPOUND_ACTION_RE.match(project_raw)
            if compound:
                project = re.sub(r"\s+today$", "", compound.group("target").strip().rstrip(","), flags=re.I)
                action_clause = compound.group("action").strip()
            else:
                project = project_raw
                action_clause = None

            presence.set_project(project)
            presence.record_action(f"Set active project: {project}")

            from backend.app.services.project_registry import find_project
            proj_info = find_project(project)
            is_node = False
            if proj_info and proj_info.get("notes"):
                is_node = any("node" in n.lower() for n in proj_info["notes"])
            if is_node:
                presence.set_node(project)

            await self._emit_tool("[PRESENCE]", f"Active project: {project}")

            if action_clause:
                action_result = await self._execute_compound_action(
                    action_clause, project, is_node, request,
                )
                if action_result:
                    answer = f"**{project}** is now active. {action_result}"
                    update_last_route("PresenceManager+Action", "Compound")
                    return self._simple_response("Project Focus + Action", answer)

            if is_node:
                answer = (
                    f"Setting **{project}** as the active workspace.\n\n"
                    f"I can open SSH, show node status, or review recent activity."
                )
            elif proj_info:
                answer = (
                    f"Setting **{project}** as the active workspace.\n\n"
                    f"I can start a work session, show project tasks, or review recent decisions."
                )
            else:
                answer = (
                    f"Setting **{project}** as the active workspace.\n\n"
                    f"All follow-up questions will be scoped to {project} until you switch."
                )

            update_last_route("PresenceManager", "Project Focus")
            return self._simple_response("Project Focus", answer)

        # "set cyberdeck as active and open fusion"
        m = self._SET_ACTIVE_RE.match(raw)
        if m:
            project = m.group("project").strip()
            rest = (m.group("rest") or "").strip()
            action_clause = None
            if rest:
                rest_m = re.match(r"^(?:,?\s*(?:and\s+)?)?(?P<action>(?:open|launch|start|run|ssh|connect|show)\s+.+)$", rest, re.I)
                if rest_m:
                    action_clause = rest_m.group("action").strip()

            presence.set_project(project)
            presence.record_action(f"Set active project: {project}")

            from backend.app.services.project_registry import find_project as _fp2
            proj_info = _fp2(project)
            is_node = bool(proj_info and proj_info.get("notes") and any("node" in n.lower() for n in proj_info["notes"]))

            await self._emit_tool("[PRESENCE]", f"Active project: {project}")

            if action_clause:
                action_result = await self._execute_compound_action(action_clause, project, is_node, request)
                if action_result:
                    answer = f"**{project}** is now active. {action_result}"
                    update_last_route("PresenceManager+Action", "Compound")
                    return self._simple_response("Project Focus + Action", answer)

            answer = f"Setting **{project}** as the active workspace."
            update_last_route("PresenceManager", "Project Focus")
            return self._simple_response("Project Focus", answer)

        m = self._WORK_SESSION_START_RE.match(raw)
        if m:
            project_raw = (m.group("project") or "").strip() or None

            # Split compound intents in work session too
            if project_raw:
                compound = self._COMPOUND_ACTION_RE.match(project_raw)
                if compound:
                    project_raw = compound.group("target").strip().rstrip(",")
                    action_clause = compound.group("action").strip()
                else:
                    action_clause = None
            else:
                action_clause = None
            project = project_raw
            result = presence.start_work_session(project)
            proj = result["project"]
            # Generate a briefing
            try:
                from backend.app.services.mission_control_service import MissionControlService
                mc = MissionControlService()
                briefing = mc.morning_briefing()
                brief_text = briefing.get("summary", "")
                tasks = briefing.get("tasks", [])
                task_text = "\n".join(f"  - {t.get('title', t)}" for t in tasks[:5]) if tasks else "  No pending tasks."
                answer = (
                    f"Work session started on **{proj}**.\n\n"
                    f"**Pending tasks:**\n{task_text}\n\n"
                    f"What would you like to work on first?"
                )
            except Exception:
                answer = (
                    f"Work session started on **{proj}**.\n\n"
                    f"What would you like to work on first?"
                )
            await self._emit_tool("[PRESENCE]", f"Work session started: {proj}")

            if action_clause:
                action_result = await self._execute_compound_action(
                    action_clause, proj, False, request,
                )
                if action_result:
                    answer += f"\n\n{action_result}"
                    update_last_route("PresenceManager+Action", "Work Session + Action")
                    return self._simple_response("Work Session + Action", answer)

            update_last_route("PresenceManager", "Work Session")
            return self._simple_response("Work Session", answer)

        if self._WORK_SESSION_END_RE.match(raw):
            result = presence.end_work_session()
            if not result.get("ended"):
                update_last_route("PresenceManager", "No Session")
                return self._simple_response("Work Session", "No active work session to end.")
            tasks = result.get("tasks_completed", [])
            actions = result.get("actions_performed", [])
            task_lines = "\n".join(f"  - {t}" for t in tasks) if tasks else "  None"
            action_lines = "\n".join(f"  - {a}" for a in actions[-10:]) if actions else "  None"
            answer = (
                f"**Work session ended** — {result['project']}\n\n"
                f"**Duration:** {result['started_at']} to {result['ended_at']}\n\n"
                f"**Tasks completed:**\n{task_lines}\n\n"
                f"**Actions performed:**\n{action_lines}"
            )
            await self._emit_tool("[PRESENCE]", f"Work session ended: {result['project']}")
            update_last_route("PresenceManager", "Session Summary")
            return self._simple_response("Session Summary", answer)

        if self._FOCUS_ON_RE.match(raw):
            presence.toggle_focus(True)
            await self._emit_tool("[PRESENCE]", "Focus mode ON")
            update_last_route("PresenceManager", "Focus On")
            return self._simple_response("Focus Mode", "Focus mode **on**. I'll only respond when spoken to — no proactive notifications.")

        if self._FOCUS_OFF_RE.match(raw):
            presence.toggle_focus(False)
            await self._emit_tool("[PRESENCE]", "Focus mode OFF")
            update_last_route("PresenceManager", "Focus Off")
            return self._simple_response("Focus Mode", "Focus mode **off**. Proactive notifications resumed.")

        if self._PRESENCE_STATUS_RE.match(raw):
            status = presence.get_status()
            proj = status["active_project"] or "None"
            task = status["active_task"] or "None"
            topic = status["active_topic"] or "None"
            focus = "On" if status["focus_mode"] else "Off"
            ws = status["work_session"]
            ws_text = f"Active ({ws['project']}, {ws['tasks_completed']} tasks)" if ws["active"] else "None"
            answer = (
                f"**Presence Status**\n\n"
                f"Project: {proj}\n"
                f"Task: {task}\n"
                f"Topic: {topic}\n"
                f"Focus Mode: {focus}\n"
                f"Work Session: {ws_text}\n"
                f"Voice State: {status['voice_state']}\n"
                f"Follow-up Window: {'Active' if status['follow_up_active'] else 'Inactive'}"
            )
            update_last_route("PresenceManager", "Status")
            return self._simple_response("Presence Status", answer)

        if self._RESET_CONTEXT_RE.match(raw):
            presence.reset()
            await self._emit_tool("[PRESENCE]", "Context reset")
            update_last_route("PresenceManager", "Reset")
            return self._simple_response("Context Reset", "Conversation context cleared. No active project, task, or topic.")

        return None

    _SSH_ACTION_RE = re.compile(
        r"^(?:open\s+(?:the\s+)?(?:ssh|remote)\s+(?:terminal|session|connection)"
        r"|ssh\s+(?:terminal|session|into\s+it|in)"
        r"|connect\s+(?:to\s+it|via\s+ssh)"
        r"|open\s+ssh)[\.\?!]?$",
        re.I,
    )
    _OPEN_APP_RE = re.compile(
        r"^(?:open|launch|start|run)\s+(?:the\s+)?(?P<apps>.+?)[\.\?!]?$",
        re.I,
    )

    async def _execute_ssh_node(self, node_name: str, username: str = "",
                               source: str = "direct") -> dict:
        """Single SSH execution function. ALL paths must use this."""
        from backend.app.tools.node_tool import open_ssh_session
        logger.info("[SSH_NODE_CALLED] node=%s source=%s", node_name, source)
        await self._emit_tool("[TOOL] ssh_node", f"Launching SSH: {node_name} (source: {source})")

        result = open_ssh_session(node_name, username)
        d = result.get("data") or {}

        await self._emit_tool(
            "[TOOL] ssh_node", result["summary"],
            "info" if result["ok"] else "error",
        )

        launched = result["ok"] and d.get("launched")
        logger.info(
            "[TERMINAL_LAUNCH_RESULT] launched=%s pid=%s node=%s error=%s",
            launched, d.get("process_id"), node_name,
            result.get("error") or "",
        )

        ver_result = CapabilityExecutionResult(
            success=result["ok"], executed=result["ok"],
            source="ssh_terminal",
            raw_output=result.get("summary", ""),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            node=node_name, capability="ssh_session", tool="ssh_node",
            error=result.get("error", "") if not result["ok"] else "",
        )
        self._verification.record_result(ver_result)
        self._last_tool_ok = result["ok"]

        if launched:
            self._verification.record_ssh_terminal(node_name)

        return result

    def _format_ssh_result(self, result: dict) -> str:
        """Build response text from an ssh_node result. Never invents success."""
        d = result.get("data") or {}
        launched = result["ok"] and d.get("launched")

        if launched:
            uname = d.get("username", "")
            key_note = f" using key `{d['key_path']}`" if d.get("key_path") else ""
            pid_note = f" (PID {d['process_id']})" if d.get("process_id") else ""
            node = result.get("node") or d.get("node") or "node"
            return (
                f"SSH terminal launched — {node} as **{uname}**{key_note}{pid_note}.\n\n"
                f"Command: `{d.get('command', '')}`\n"
                f"Provider: {d.get('provider', 'unknown')}\n\n"
                f"Type commands directly in the SSH window."
            )
        error = result.get("error") or "unknown error"
        cmd = d.get("command")
        msg = f"SSH terminal launch failed: {error}"
        if cmd:
            msg += f"\n\nCommand attempted: `{cmd}`"
        return msg

    _CONTEXTUAL_SSH_RE = re.compile(
        r"^(?:open\s+(?:the\s+)?(?:ssh|remote)\s+(?:terminal|session|connection)"
        r"|open\s+ssh"
        r"|ssh\s+(?:terminal|session|in(?:to\s+it)?)"
        r"|connect(?:\s+via\s+ssh)?"
        r")[\s\.\?!]*$",
        re.I,
    )

    _EXPLICIT_NODE_SSH_RE = re.compile(
        r"^(?:ssh(?:\s+into?)?|connect(?:\s+to)?)\s+(\w+)", re.I,
    )

    async def _handle_contextual_ssh(self, raw: str, presence, request) -> "AssistantResponse | None":
        """Handle SSH commands, resolving target from presence context when needed."""
        # If the query names a node explicitly, extract it and launch directly
        m = self._EXPLICIT_NODE_SSH_RE.match(raw)
        if m:
            node_name = m.group(1).strip()
            username_m = re.search(r"\bas\s+([a-zA-Z0-9_.\-]+)$", raw, re.I)
            username = username_m.group(1) if username_m else ""
            result = await self._execute_ssh_node(node_name, username, source="direct")
            answer = self._format_ssh_result(result)
            update_last_route("SSH", "Direct")
            return self._node_response("SSH Session" if result["ok"] else "SSH Failed", answer, result)

        # No explicit node — resolve from presence context
        if not self._CONTEXTUAL_SSH_RE.match(raw):
            return None

        node_target = presence.active_node
        project = presence.active_project

        if node_target:
            logger.info("Contextual SSH: using active_node=%s", node_target)
            await self._emit_tool("[SSH]", f"Context resolve: active node = {node_target}")
            result = await self._execute_ssh_node(node_target, "", source="context_node")
            answer = self._format_ssh_result(result)
            update_last_route("SSH", f"Context -> {node_target}")
            return self._node_response("SSH Session" if result["ok"] else "SSH Failed", answer, result)

        if project:
            from backend.app.services.project_registry import find_project
            proj_info = find_project(project)
            if proj_info and proj_info.get("notes") and any("node" in n.lower() for n in proj_info["notes"]):
                logger.info("Contextual SSH: project %s is a node", project)
                await self._emit_tool("[SSH]", f"Context resolve: project {project} is a node")
                result = await self._execute_ssh_node(project, "", source="context_project_node")
                answer = self._format_ssh_result(result)
                update_last_route("SSH", f"Context -> {project}")
                return self._node_response("SSH Session" if result["ok"] else "SSH Failed", answer, result)

            await self._emit_tool("[SSH]", f"No SSH target: project '{project}' is not a node", "warning")
            update_last_route("SSH", "No Target")
            return self._simple_response(
                "SSH — No Target",
                f"Active project is **{project}**, but it's not an SSH node.\n\n"
                f"Specify a node: `ssh <node_name>`",
            )

        update_last_route("SSH", "No Context")
        return self._simple_response(
            "SSH — No Target",
            "No active node or project. Specify a node: `ssh <node_name>`",
        )

    async def _execute_compound_action(
        self, action: str, project: str, is_node: bool, request
    ) -> str | None:
        """Execute an action clause extracted from a compound presence command."""
        action_stripped = action.strip()
        logger.info("Compound action: project=%r action=%r is_node=%s", project, action_stripped, is_node)
        await self._emit_tool("[COMPOUND]", f"Action: {action_stripped} (context: {project})")

        if self._SSH_ACTION_RE.match(action_stripped):
            result = await self._execute_ssh_node(project, "", source="mixed_intent")
            return self._format_ssh_result(result)

        m = self._OPEN_APP_RE.match(action_stripped)
        if m:
            from backend.app.tools.planner import _regex_desktop
            app_target = m.group("apps").strip()
            desk_route = _regex_desktop(f"open {app_target}")
            if desk_route and desk_route.get("action") in ("call_tool", "call_tools"):
                tool_resp = await self._execute_plan(desk_route, request)
                if tool_resp:
                    return tool_resp.answer
            from backend.app.tools.planner import plan
            tool_decision = await plan(action_stripped, allow_web=False)
            if tool_decision.get("action") in ("call_tool", "call_tools"):
                tool_resp = await self._execute_plan(tool_decision, request)
                if tool_resp:
                    return tool_resp.answer

        return None
    # ── End Presence Mode ──────────────────────────────────────────────────

    async def _handle_approval_command(self, raw: str, request) -> AssistantResponse | None:
        """Handle approve/reject commands for the safety framework."""
        m = _APPROVE_RE.match(raw.strip())
        if m:
            code = m.group("code").upper()
            from backend.app.services.approval_manager import get_approval_manager
            am = get_approval_manager()
            result = am.approve(code)
            if not result.get("ok"):
                return self._simple_response("Approval", result.get("error", "Could not approve."))
            # Execute the approved tool
            tool_name = result.get("tool_name", "")
            tool_args = result.get("args", {})
            await self._emit_tool("[SAFETY] approved", f"{code}: executing {tool_name}", "info")
            self._last_tool_ok = True
            exec_result = await self._run_tool_bypassing_safety(tool_name, tool_args)
            if self._last_tool_ok:
                am.mark_executed(code)
                await self._emit_tool("[VERIFICATION] execution_succeeded", f"{code}: {tool_name}", "info")
            else:
                await self._emit_tool("[VERIFICATION] execution_failed", f"{code}: {tool_name} returned failure", "error")
            if exec_result:
                return exec_result
            return self._simple_response("Approved", f"Approved and executed {code}.")

        m = _REJECT_RE.match(raw.strip())
        if m:
            code = m.group("code").upper()
            from backend.app.services.approval_manager import get_approval_manager
            result = get_approval_manager().reject(code)
            if not result.get("ok"):
                return self._simple_response("Rejection", result.get("error", "Could not reject."))
            return self._simple_response("Rejected", f"Rejected {code}. Action will not be executed.")

        if _APPROVE_ALL_RE.match(raw.strip()):
            from backend.app.services.approval_manager import get_approval_manager
            result = get_approval_manager().approve_all_pending(session_id=request.session_id)
            count = result.get("approved_count", 0)
            if count == 0:
                return self._simple_response("Approvals", "No pending approvals to approve.")
            # Execute all approved
            executed = 0
            for apr in result.get("approved", []):
                tool_name = apr.get("tool_name", "")
                tool_args = apr.get("args", {})
                exec_result = await self._run_tool_bypassing_safety(tool_name, tool_args)
                if exec_result:
                    get_approval_manager().mark_executed(apr.get("approval", {}).get("code", ""))
                    executed += 1
            return self._simple_response("Approvals", f"Approved and executed {executed} action(s).")

        if _REJECT_ALL_RE.match(raw.strip()):
            from backend.app.services.approval_manager import get_approval_manager
            result = get_approval_manager().reject_all_pending(session_id=request.session_id)
            count = result.get("rejected_count", 0)
            return self._simple_response("Rejections", f"Rejected {count} pending approval(s)." if count else "No pending approvals.")

        # "yes" on a pending approval
        if _YES_RE.match(raw.strip()):
            from backend.app.services.approval_manager import get_approval_manager
            pending = get_approval_manager().find_pending_for_session(request.session_id)
            if pending:
                code = pending["code"]
                result = get_approval_manager().approve(code)
                if result.get("ok"):
                    tool_name = result.get("tool_name", "")
                    tool_args = result.get("args", {})
                    await self._emit_tool("[SAFETY] approved", f"{code}: executing {tool_name}", "info")
                    exec_result = await self._run_tool_bypassing_safety(tool_name, tool_args)
                    get_approval_manager().mark_executed(code)
                    if exec_result:
                        return exec_result
                    return self._simple_response("Approved", f"Approved and executed {code}.")

        return None

    async def _run_tool_bypassing_safety(self, name: str, args: dict) -> AssistantResponse | None:
        """Execute a tool without the safety gate (for approved actions)."""
        self._bypass_safety = True
        try:
            return await self._run_tool(name, args)
        finally:
            self._bypass_safety = False

    # ── Phase 17B: Workflow commands ────────────────────────────────────────

    async def _execute_approved_workflow(
        self, code: str, tool_name: str, tool_args: dict
    ) -> AssistantResponse:
        """Execute a tool after workflow approval with full verification.

        Every path through workflow approval MUST use this method. It
        guarantees that:
        - The workflow is marked executing before the tool runs
        - The tool result is verified (not just "did it return something")
        - The workflow is marked completed or failed based on actual result
        - A None result from _run_tool is treated as failure, not success
        - The execution result is stored in the workflow record
        """
        from backend.app.services.workflow_engine import get_workflow_engine
        we = get_workflow_engine()

        we.mark_executing(code)
        await self._emit_tool("[WORKFLOW] approved", f"{code}: executing {tool_name}", "info")

        try:
            self._last_tool_ok = True
            exec_result = await self._run_tool_bypassing_safety(tool_name, tool_args)

            if exec_result is None:
                we.mark_failed(code, "Tool returned no result")
                await self._emit_tool("[WORKFLOW] execution_failed", f"{code}: tool returned None", "error")
                return self._simple_response(
                    "Workflow Failed",
                    f"Workflow {code} approved but execution produced no verified result.\n\n"
                    f"Tool `{tool_name}` did not return a result. No action was taken.",
                )

            tool_failed = (
                not self._last_tool_ok
                or (exec_result.title and "Failed" in exec_result.title)
            )
            if tool_failed:
                we.mark_failed(code, json.dumps({
                    "executed": True,
                    "success": False,
                    "executor": tool_name,
                    "raw_output": exec_result.answer[:500] if exec_result else "",
                    "error": "Tool reported failure",
                }))
                await self._emit_tool("[WORKFLOW] execution_failed", f"{code}: tool returned failure", "error")
                from backend.app.services.execution_ledger import get_ledger
                get_ledger().log_execution(
                    intent=f"workflow {code}", tool=tool_name,
                    status="failure", message=f"Workflow {code} approved but tool failed",
                )
                return exec_result

            we.mark_completed(code, json.dumps({
                "executed": True,
                "success": True,
                "executor": tool_name,
                "raw_output": exec_result.answer[:500] if exec_result else "",
            }))
            await self._emit_tool("[WORKFLOW] execution_succeeded", f"{code}: completed", "info")
            return exec_result

        except Exception as e:
            we.mark_failed(code, json.dumps({
                "executed": False,
                "success": False,
                "executor": tool_name,
                "error": str(e),
            }))
            await self._emit_tool("[WORKFLOW] execution_failed", f"{code}: exception — {e}", "error")
            return self._simple_response(
                "Workflow Failed",
                f"Workflow {code} approved but execution failed: {e}",
            )

    async def _handle_workflow_command(self, raw: str, request) -> AssistantResponse | None:
        """Handle workflow approve/reject/cancel commands."""
        m = _WF_APPROVE_RE.match(raw.strip())
        if m:
            code = m.group("code").upper()
            from backend.app.services.workflow_engine import get_workflow_engine
            we = get_workflow_engine()
            result = we.approve(code)
            if not result.get("ok"):
                return self._simple_response("Workflow", result.get("error", "Could not approve."))
            tool_name = result.get("tool_name", "")
            tool_args = result.get("tool_args", {})
            if tool_name:
                return await self._execute_approved_workflow(code, tool_name, tool_args)
            return self._simple_response("Approved", f"Approved workflow {code}. (No executable action attached.)")

        m = _WF_REJECT_RE.match(raw.strip())
        if m:
            code = m.group("code").upper()
            from backend.app.services.workflow_engine import get_workflow_engine
            result = get_workflow_engine().reject(code)
            if not result.get("ok"):
                return self._simple_response("Workflow", result.get("error", "Could not reject."))
            return self._simple_response("Rejected", f"Rejected workflow {code}. Action will not be executed.")

        m = _WF_CANCEL_RE.match(raw.strip())
        if m:
            code = m.group("code").upper()
            from backend.app.services.workflow_engine import get_workflow_engine
            result = get_workflow_engine().cancel(code)
            if not result.get("ok"):
                return self._simple_response("Workflow", result.get("error", "Could not cancel."))
            return self._simple_response("Cancelled", f"Cancelled workflow {code}.")

        if _WF_APPROVE_ALL_RE.match(raw.strip()):
            from backend.app.services.workflow_engine import get_workflow_engine
            we = get_workflow_engine()
            max_risk = "low" if "low risk" in raw.lower() else ""
            result = we.approve_all_pending(session_id=request.session_id, max_risk=max_risk)
            count = result.get("approved_count", 0)
            if count == 0:
                return self._simple_response("Workflows", "No pending workflows to approve.")
            executed = 0
            failed = 0
            for wf_result in result.get("approved", []):
                tool_name = wf_result.get("tool_name", "")
                tool_args = wf_result.get("tool_args", {})
                wf_code = wf_result.get("workflow", {}).get("code", "")
                if tool_name:
                    try:
                        await self._execute_approved_workflow(wf_code, tool_name, tool_args)
                        if self._last_tool_ok:
                            executed += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
            summary = f"Approved {count} workflow(s): {executed} executed"
            if failed:
                summary += f", {failed} failed"
            return self._simple_response("Workflows", summary + ".")

        if _WF_REJECT_ALL_RE.match(raw.strip()):
            from backend.app.services.workflow_engine import get_workflow_engine
            result = get_workflow_engine().reject_all_pending(session_id=request.session_id)
            count = result.get("rejected_count", 0)
            return self._simple_response("Workflows", f"Rejected {count} pending workflow(s)." if count else "No pending workflows.")

        # "yes" on a pending workflow
        if _YES_RE.match(raw.strip()):
            from backend.app.services.workflow_engine import get_workflow_engine
            we = get_workflow_engine()
            pending = we.find_pending_for_session(request.session_id)
            if pending:
                code = pending["code"]
                result = we.approve(code)
                if not result.get("ok"):
                    return self._simple_response("Workflow", result.get("error", "Could not approve."))
                tool_name = result.get("tool_name", "")
                tool_args = result.get("tool_args", {})
                if tool_name:
                    return await self._execute_approved_workflow(code, tool_name, tool_args)
                return self._simple_response("Approved", f"Approved workflow {code}. (No executable action attached.)")

        return None

    def _get_workflow_category(self, tool_name: str) -> str:
        """Map a tool name to a workflow category."""
        _TOOL_CATEGORIES = {
            "ssh_node": "infrastructure",
            "run_command": "infrastructure",
            "send_node_command": "infrastructure",
            "send_bulk_command": "infrastructure",
            "fleet_action": "infrastructure",
            "execute_capability": "service_action",
            "remove_node_service": "service_action",
            "delete_node": "infrastructure",
            "delete_task": "project_change",
            "delete_reminder": "project_change",
            "delete_scheduled_task": "project_change",
            "delete_calendar_event": "calendar_change",
            "send_email": "email_action",
        }
        return _TOOL_CATEGORIES.get(tool_name, "service_action")

    def _build_workflow_title(self, tool_name: str, args: dict) -> str:
        """Build a human-readable workflow title."""
        target = args.get("node", args.get("project", args.get("name", args.get("query", ""))))
        action = tool_name.replace("_", " ").title()
        if target:
            return f"{action} — {target}"
        return action

    def _build_workflow_description(self, tool_name: str, args: dict) -> str:
        """Build a workflow description with impact details."""
        lines = []
        target = args.get("node", args.get("project", args.get("name", "")))

        if tool_name in ("ssh_node", "run_command"):
            cmd = args.get("cmd", args.get("command", ""))
            if cmd:
                lines.append(f"Command: {cmd}")
            if target:
                lines.append(f"Target: {target}")
            lines.append("Impact: Direct infrastructure access.")

        elif tool_name in ("send_node_command", "send_bulk_command"):
            cmd = args.get("command", "")
            lines.append(f"Command: {cmd}")
            if target:
                lines.append(f"Target: {target}")
            ntype = args.get("type", "")
            if ntype:
                lines.append(f"Node type: {ntype}")
            lines.append("Impact: Node state will change.")

        elif tool_name == "fleet_action":
            cap = args.get("capability", "")
            ftype = args.get("filter_type", "")
            fval = args.get("filter_value", "")
            svc = args.get("service_name", "")
            lines.append(f"Capability: {cap}")
            if svc:
                lines.append(f"Service: {svc}")
            lines.append(f"Filter: {ftype}={fval}")
            lines.append("Impact: Multiple nodes affected.")

        elif tool_name == "send_email":
            lines.append(f"To: {args.get('to', '')}")
            lines.append(f"Subject: {args.get('subject', '')}")
            lines.append("Impact: Email will be sent externally.")

        elif tool_name == "delete_calendar_event":
            lines.append(f"Event: {args.get('title', args.get('event_id', ''))}")
            lines.append("Impact: Calendar event will be permanently deleted.")

        elif tool_name in ("delete_node", "delete_task", "delete_reminder", "delete_scheduled_task"):
            lines.append(f"Target: {target or args.get('query', '')}")
            lines.append("Impact: Permanent deletion.")

        else:
            if target:
                lines.append(f"Target: {target}")

        return "\n".join(lines)

    def _render_workflow_card(self, wf: dict) -> AssistantResponse:
        """Render a workflow review card."""
        risk_labels = {"read": "Read", "low": "Low", "moderate": "Moderate", "high": "High", "critical": "Critical"}
        risk = wf.get("risk_level", "moderate")
        risk_display = risk_labels.get(risk, risk.title())
        code = wf.get("code", "???")
        title = wf.get("title", "Unknown")
        category = wf.get("category", "").replace("_", " ").title()
        description = wf.get("description", "")
        diff = wf.get("diff_text", "")
        expires = wf.get("expires_at", "")[:16].replace("T", " ")
        affected = wf.get("affected", [])
        affected_str = ", ".join(a for a in affected if a)

        lines = [
            f"Workflow {code} requires review.",
            "",
            f"Title: {title}",
            f"Category: {category}",
            f"Risk: {risk_display}",
        ]
        if affected_str:
            lines.append(f"Affected: {affected_str}")
        if description:
            lines.append("")
            lines.append(description)
        if diff:
            lines.append("")
            lines.append(diff)
        lines.append("")
        lines.append(f"Expires: {expires} UTC")
        lines.append("")
        lines.append(f"Reply: approve {code}")
        lines.append(f"   or: reject {code}")
        lines.append(f"   or: cancel {code}")

        return AssistantResponse(
            mode="conversation",
            answer="\n".join(lines),
            title=f"Workflow Review — {code}",
            processing_time_ms=0,
            payload={
                "workflow": {
                    "code": code,
                    "title": title,
                    "category": category,
                    "risk": risk_display,
                    "description": description,
                    "affected": affected_str,
                    "expires": expires,
                    "status": "pending_review",
                    "diff": diff,
                },
            },
        )

    def _handle_user_correction(self, raw: str) -> AssistantResponse | None:
        """Detect and store user corrections about known entities.

        'Nighthawk is just a Pi NAS' → stored; 'nighthawk doesn't have a camera' → stored.
        Does NOT fire on 'nighthawk is online' (state assertions are handled separately).
        """
        m = _USER_CORRECTION_RE.match(raw)
        if not m:
            return None

        groups = m.groups()
        # Pattern groups: (entity_positive, desc_positive, entity_negative, desc_negative)
        entity = groups[0] or groups[2]
        description = groups[1] or groups[3]
        if not entity or not description:
            return None

        from backend.app.services.device_registry import get_device, DEVICE_REGISTRY
        from backend.app.services.project_registry import find_project

        entity_clean = entity.lower().strip()
        known = get_device(entity_clean) is not None or find_project(entity_clean) is not None
        if not known:
            return None

        if self.memory_service:
            key = f"correction_{re.sub(r'[^a-z0-9]', '_', entity_clean)}"
            self.memory_service.remember(key, description.strip().rstrip(".!?"))

        display = (DEVICE_REGISTRY.get(entity_clean) or {}).get("display_name", entity)
        return self._simple_response(
            "Noted",
            f"Noted — I've updated my record for {display}.",
        )

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

    def _tool_coda(self, target: str) -> str:
        """Occasional dry contextual follow-up appended to an action result.

        Deterministic (template-based, no LLM), debounced per action type so
        it stays occasional. Empty string when debounce is active or no coda
        is appropriate for this target.
        """
        import random
        t = target.lower()
        if any(k in t for k in ("spotify", "soundcloud", "apple music", "youtube music", "tidal", "deezer")):
            return self._maybe_suggest("coda_music", random.choice([
                " Working session or procrastinating?",
                " Focus playlist or the dangerous kind?",
                " Good choice.",
            ]), cooldown=1800.0)
        if any(k in t for k in ("code", "vscode", "visual studio")):
            return self._maybe_suggest("coda_code", random.choice([
                " New feature or bug hunt?",
                " What are we getting into?",
            ]), cooldown=3600.0)
        if any(k in t for k in ("youtube",)) and "music" not in t:
            return self._maybe_suggest("coda_youtube", random.choice([
                " Research or the other kind?",
                " Learning something or taking a break?",
            ]), cooldown=3600.0)
        return ""

    def _maybe_suggest(self, key: str, text: str, cooldown: float = 600.0) -> str:
        """Return a proactive follow-up offer, or "" if one fired recently.

        Keeps suggestions occasional — a fixed offer after every action reads
        as boilerplate, which is the opposite of presence.
        """
        now = time.monotonic()
        if now - self._last_suggested.get(key, -cooldown) < cooldown:
            return ""
        self._last_suggested[key] = now
        return text

    async def _handle_local_command(self, request: AssistantRequest) -> AssistantResponse | None:
        raw = strip_wake_prefix(request.query.strip())
        lowered = raw.lower()

        # Last voice follow-up decision (debug)
        if _VOICE_DECISION_RE.search(lowered):
            d = _LAST_VOICE_DECISION
            if not d:
                return self._simple_response(
                    "Last Voice Decision",
                    "No voice decision recorded yet. Speak to SILVIA (a voice turn), then ask again.",
                )
            body = "\n".join([
                f"**Response:** \"{d.get('response', '')}\"",
                f"**expects_reply:** {str(d.get('expects_reply', False)).lower()}",
                f"**followup_reason:** {d.get('followup_reason', 'none')}",
                f"**next_state:** {d.get('next_state', 'WAKE_LISTENING')}",
                f"**why:** {d.get('why', '')}",
                f"**at:** {d.get('ts', '')}",
            ])
            return self._simple_response("Last Voice Decision", body)

        # Chat / LLM latency report — phase breakdown of recent replies
        if _CHAT_LATENCY_RE.search(lowered):
            if not _LLM_TIMINGS:
                return self._simple_response(
                    "Chat Latency",
                    "No chat replies measured yet. Ask SILVIA a question, then run this again.\n\n"
                    "Phases tracked: **ttft** (time to first token — the 'thinking' delay), "
                    "**ctx** (context build, incl. **mem** = embedding search), "
                    "**gen** (generation), **tok/s** (throughput).",
                )
            recent = list(_LLM_TIMINGS)[-8:]
            n = len(recent)
            avg = lambda k: sum(r[k] for r in recent) / n
            lines = [
                f"**Model:** {recent[-1]['model']}   (last {n} replies)",
                f"**Avg time-to-first-token:** {avg('ttft_ms'):.0f} ms  ← the 'understanding' delay you feel",
                f"**Avg context build:** {avg('ctx_ms'):.0f} ms  (embedding/memory search: {avg('mem_ms'):.0f} ms, "
                f"brain63: {avg('brain63_ms'):.0f} ms, nodes: {avg('node_ms'):.0f} ms)",
                f"**Avg generation:** {avg('gen_ms'):.0f} ms  @ {avg('tok_s'):.1f} tok/s",
                f"**Avg prompt size:** {avg('prompt_chars'):.0f} chars",
                "",
                "Recent replies (newest first):",
            ]
            for r in reversed(recent):
                lines.append(
                    f"  `{r['ts']}` ttft={r['ttft_ms']}ms ctx={r['ctx_ms']}ms "
                    f"(mem={r['mem_ms']}) gen={r['gen_ms']}ms {r['tok_s']}tok/s "
                    f"[{r['goal']}] — {r['query']!r}"
                )
            # Inline guidance based on what dominates
            a_ttft, a_mem, a_gen, a_toks = avg("ttft_ms"), avg("mem_ms"), avg("gen_ms"), avg("tok_s")
            lines.append("")
            if a_mem > 400:
                lines.append("⚠️ Embedding/memory search is a big share of the delay — the embed model may be reloading. The keep-alive fix should reduce this after a few queries.")
            if a_ttft - a_mem > 1500:
                lines.append("⚠️ High time-to-first-token beyond memory search points to a model reload (VRAM swap) or large prompt — likely a GPU-memory constraint.")
            if a_toks and a_toks < 12:
                lines.append("⚠️ Low tokens/sec suggests CPU inference (no GPU). A smaller model would be the main lever.")
            elif a_toks >= 25:
                lines.append("✅ Healthy tokens/sec — generation is GPU-fast; latency is mostly pre-token (context/first-token).")
            return self._simple_response("Chat Latency", "\n".join(lines))

        # Voice latency report
        if _VOICE_LATENCY_RE.search(lowered):
            from backend.app.voice.pipeline_fast import get_latency_logger
            lat = get_latency_logger()
            text = lat.summary_text(10)
            return self._simple_response("Voice Pipeline Latency", text)

        # Voice mode report
        if _VOICE_MODE_RE.search(lowered):
            from backend.config import (
                VOICE_MODE, VOICE_SUPPORTED_MODES, VOICE_AUTO_TTS, VOICE_FOLLOWUP_ENABLED,
            )
            presence = VOICE_MODE == "presence_experimental"
            lines = [
                f"**Current voice mode:** {VOICE_MODE}",
                f"**Supported modes:** {', '.join(VOICE_SUPPORTED_MODES)}",
                f"**Auto TTS enabled:** {str(VOICE_AUTO_TTS and presence).lower()}",
                f"**Follow-up listening:** {str(VOICE_FOLLOWUP_ENABLED and presence).lower()}",
                f"**Presence (conversational) mode:** {'enabled' if presence else 'disabled'}",
                "",
                "Stable flow: wake word → record one utterance → transcribe → send to chat "
                "as text. No automatic speech — use the play/replay button to hear a response.",
            ]
            return self._simple_response("Voice Mode", "\n".join(lines))

        # Voice diagnostics — overall pipeline health for the stable STT-only path
        if _VOICE_DIAG_RE.search(lowered):
            from backend.config import (
                VOICE_MODE, STT_PROVIDER, TTS_PROVIDER, VOICE_AUTO_TTS,
                VOICE_FOLLOWUP_ENABLED,
            )
            from backend.app.api.voice import _tts_diag, _inject_queues
            presence = VOICE_MODE == "presence_experimental"
            try:
                from backend.voice.wakeword.detector import get_detector
                wd = get_detector().diagnostics()
                wake_status = (
                    f"model_loaded={wd['model_loaded']} chunks={wd['chunks_processed']} "
                    f"last_conf={wd['last_confidence']:.3f}"
                )
            except Exception as exc:
                wake_status = f"unavailable ({exc})"
            tts_queue = _tts_diag.get("queueSize", 0) if _tts_diag else 0
            tts_playing = bool(_tts_diag.get("currentlyPlaying", False)) if _tts_diag else False
            lines = [
                f"**Voice mode:** {VOICE_MODE}",
                f"**Wake listener:** {len(_inject_queues)} active connection(s) — {wake_status}",
                f"**STT provider:** {STT_PROVIDER}",
                f"**TTS provider:** {TTS_PROVIDER} (manual replay only)",
                f"**TTS auto enabled:** {str(VOICE_AUTO_TTS and presence).lower()}",
                f"**TTS queue size:** {tts_queue}",
                f"**Pending playback:** {str(tts_playing).lower()}",
                f"**Follow-up enabled:** {str(VOICE_FOLLOWUP_ENABLED and presence).lower()}",
                f"**Presence mode:** {'enabled' if presence else 'disabled'}",
            ]
            return self._simple_response("Voice Diagnostics", "\n".join(lines))

        # TTS diagnostics (pushed from browser after each turn)
        if _TTS_DIAG_RE.search(lowered):
            from backend.app.api.voice import _tts_diag
            from backend.config import TTS_PROVIDER, SPEACHES_TTS_MODEL, SPEACHES_TTS_VOICE, SPEACHES_BASE_URL
            if not _tts_diag:
                body = (
                    "No TTS diagnostics received yet. Ask SILVIA a voice question first, "
                    "then run this command.\n\n"
                    f"**Provider:** {TTS_PROVIDER} ({SPEACHES_BASE_URL})\n"
                    f"**Model:** {SPEACHES_TTS_MODEL}\n"
                    f"**Voice:** {SPEACHES_TTS_VOICE}"
                )
                return self._simple_response("TTS Diagnostics", body)

            d = _tts_diag
            lines = [
                f"**Provider:** {d.get('provider', TTS_PROVIDER)} — {SPEACHES_BASE_URL}",
                f"**Model:** {SPEACHES_TTS_MODEL}  Voice: {SPEACHES_TTS_VOICE}",
                f"**Active turn:** {d.get('activeTurnId') or 'none'}",
                f"**Currently playing:** {d.get('currentlyPlaying', False)}",
                f"**Queue size:** {d.get('queueSize', 0)}  Pending chunks: {d.get('pendingChunks', 0)}",
                f"**Total turns:** {d.get('totalTurns', 0)}  Total chunks sent: {d.get('totalChunksSent', 0)}",
                f"**History rejections:** {d.get('historyRejections', 0)}",
                f"**Cancelled turns (last 5):** {', '.join(d.get('cancelledTurns', [])) or 'none'}",
                f"**Last text sent:** {d.get('lastTextSentToTts') or 'none'}",
                f"**Last error:** {d.get('lastTtsError') or 'none'}",
            ]
            return self._simple_response("TTS Diagnostics", "\n".join(lines))

        # Wake word diagnostics
        if _WAKE_DIAG_RE.search(lowered):
            from backend.config import (
                VOICE_MODE, WAKE_WORD_THRESHOLD, WAKE_WORD_COOLDOWN_SECONDS,
                WAKE_BYPASS_COOLDOWN_CONFIDENCE, WAKE_CONFIRMATION_ENABLED,
                WAKE_MIN_COMMAND_WORDS,
            )
            cooldown_label = f"{WAKE_WORD_COOLDOWN_SECONDS}s" if WAKE_WORD_COOLDOWN_SECONDS > 0 else "disabled (0)"
            lines = [
                f"**VOICE_MODE:** {VOICE_MODE}",
                f"**Wake word enabled:** true",
                f"**Threshold:** {WAKE_WORD_THRESHOLD}",
                f"**Cooldown:** {cooldown_label} (bypassed if confidence ≥ {WAKE_BYPASS_COOLDOWN_CONFIDENCE})",
                f"**Confirmation required:** {WAKE_CONFIRMATION_ENABLED}",
                f"**Min command words:** {WAKE_MIN_COMMAND_WORDS}",
            ]
            try:
                from backend.voice.wakeword.detector import get_detector
                d = get_detector().diagnostics()
                lines += [
                    "",
                    f"**Model:** {d['model']} (loaded: {d['model_loaded']})",
                    f"**Chunks processed:** {d['chunks_processed']}",
                    f"**Last confidence:** {d['last_confidence']:.3f} (raw: {d['last_raw_confidence']:.3f})",
                    f"**Last audio level (RMS):** {d['last_audio_level']:.5f}",
                    f"**Cooldown active:** {d['in_cooldown']} (remaining: {d['cooldown_remaining_s']}s)",
                    f"**Total accepted:** {d['total_accepted_triggers']} | cooldown bypassed: {d.get('cooldown_bypassed', 0)}",
                    f"**Rejected — below threshold:** {d['rejected_below_threshold']}",
                    f"**Rejected — cooldown:** {d['rejected_cooldown']}",
                    f"**Last state:** {d['last_state_transition']}",
                    f"**Last error:** {d['last_error'] or 'none'}",
                ]
                if not d["model_loaded"]:
                    lines.append("\n⚠️ **Model failed to load.** Check hey_silvia.onnx and openwakeword install.")
                elif d["chunks_processed"] == 0:
                    lines.append("\n⚠️ **No audio received.** Wake WebSocket may not be connected — check browser mic permission and voice toggle.")
                elif d["last_audio_level"] < 0.001:
                    lines.append("\n⚠️ **Very low audio level.** Mic may be muted or wrong device selected.")
                elif d["in_cooldown"]:
                    lines.append(f"\n⚠️ **Cooldown active** ({d['cooldown_remaining_s']:.1f}s left). Say 'reset wake cooldown' to clear it.")
                elif d["last_confidence"] > 0 and d["last_confidence"] < d["threshold"]:
                    lines.append(f"\n⚠️ **Confidence below threshold.** Speak louder or closer. Current: {d['last_confidence']:.3f} / need: {d['threshold']:.2f}.")
                else:
                    lines.append("\n✅ Wake word detector looks healthy. Say 'Hey Silvia' clearly.")
            except Exception as exc:
                lines.append(f"\n⚠️ Wake word detector not initialized: {exc}")
            return self._simple_response("Wake Word Diagnostics", "\n".join(lines))

        # Reset wake cooldown
        if _WAKE_RESET_RE.search(lowered):
            try:
                from backend.voice.wakeword.detector import get_detector
                get_detector().reset_cooldown()
                return self._simple_response("Wake Cooldown Reset", "Wake word cooldown cleared. SILVIA is ready to detect 'Hey Silvia' again.")
            except Exception as exc:
                return self._simple_response("Wake Reset Failed", f"Could not reset cooldown: {exc}")

        # Pending email send confirmation (Phase 12G)
        if self._pending_email:
            pending = self._pending_email
            if re.match(r"^(?:no|cancel|abort|stop|nevermind|nope)[\s\.!]*$", lowered):
                self._pending_email = None
                return self._simple_response("Cancelled", "Email not sent.")
            if re.match(r"^(?:yes|confirm|send|proceed|do\s+it|affirmative)[\s,\.!]*$", lowered):
                self._pending_email = None
                await self._emit_tool("[TOOL] send_email", f"Sending email to {pending['to']}")
                from backend.app.tools.productivity_tool import send_email_confirmed
                result = send_email_confirmed(pending["to"], pending["subject"], pending["body"])
                await self._emit_tool("[TOOL] send_email", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response("Email Sent" if result["ok"] else "Send Failed", result["summary"], result)

        # Pending Google Calendar event delete confirmation (Phase 12G)
        if self._pending_gcal_delete:
            pending = self._pending_gcal_delete
            if re.match(r"^(?:no|cancel|abort|stop|nevermind|nope)[\s\.!]*$", lowered):
                self._pending_gcal_delete = None
                return self._simple_response("Cancelled", "Calendar event not deleted.")
            if re.match(r"^(?:yes|confirm|proceed|do\s+it|delete|affirmative)[\s,\.!]*$", lowered):
                self._pending_gcal_delete = None
                await self._emit_tool("[TOOL] delete_gcal_event", f"Deleting event: {pending.get('title', pending['event_id'])}")
                from backend.app.tools.productivity_tool import delete_gcal_event_confirmed
                result = delete_gcal_event_confirmed(pending["event_id"], pending.get("title", ""))
                await self._emit_tool("[TOOL] delete_gcal_event", result["summary"], "info" if result["ok"] else "error")
                return self._personal_response("Event Deleted" if result["ok"] else "Delete Failed", result["summary"], result)

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
                if result["ok"] and result.get("data"):
                    await self.event_service.emit_ws_only({
                        "type": "node_deleted",
                        "node_id": result["data"]["node_id"],
                    })
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
                result = await self._execute_ssh_node(pending["node"], username, source="pending_username")
                answer = self._format_ssh_result(result)
                return self._node_response("SSH Session" if result["ok"] else "SSH Failed", answer, result)

        # Pending node command confirmation
        if self._pending_command:
            pending = self._pending_command
            if re.match(r"^(?:no|cancel|abort|stop|nevermind|nope)[\s\.!]*$", lowered):
                self._pending_command = None
                if pending.get("_create_node_for_service"):
                    return self._simple_response("Cancelled", "Node creation cancelled.")
                if pending.get("_capability"):
                    return self._simple_response("Cancelled", f"Capability '{pending['_capability']}' cancelled.")
                if "_fleet_action" in pending:
                    fa = pending["_fleet_action"]
                    return self._simple_response(
                        "Cancelled",
                        f"Fleet action '{fa['capability']}' cancelled.",
                    )
                await self._emit_tool(
                    "[TOOL] send_node_command",
                    f"Cancelled — '{pending.get('command','?')}' on '{pending.get('node','?')}' aborted",
                    "warning",
                )
                return self._simple_response(
                    "Cancelled",
                    f"Command '{pending.get('command','?')}' on '{pending.get('node','?')}' aborted.",
                )
            if re.match(r"^(?:yes|confirm|proceed|do\s+it|affirmative)[\s,\.!]*$", lowered):
                self._pending_command = None
                # Create node then apply service tool
                if pending.get("_create_node_for_service"):
                    node_name = pending["_node_name"]
                    then = pending["_then"]
                    from backend.app.tools.node_tool import create_node_entry
                    loop = __import__("asyncio").get_event_loop()
                    node_result = await loop.run_in_executor(None, create_node_entry, node_name, "")
                    if not node_result["ok"]:
                        return self._simple_response("Create Node Failed", node_result["summary"])
                    # Emit node_added WS event
                    if self.event_service and node_result.get("data"):
                        from backend.app.services.node_service import NodeService as _NS
                        _new_node = _NS().get_node(node_result["data"]["id"])
                        if _new_node:
                            await self.event_service.emit_ws_only({
                                "type": "node_added",
                                "node": _new_node.model_dump(),
                            })
                    # Now apply the queued service tool
                    tool_name = then.get("tool")
                    if tool_name == "register_node_preset":
                        return await self._run_tool("register_node_preset",
                                                    {"node": node_name, "preset": then.get("preset", "")})
                    if tool_name == "add_node_service":
                        return await self._run_tool("add_node_service", {
                            "node": node_name,
                            "service": then.get("service", ""),
                            "type": then.get("type", ""),
                            "description": then.get("description", ""),
                        })
                    return self._simple_response("Node Created", f"Node '{node_name}' created.")

                # Fleet action confirmation
                if "_fleet_action" in pending:
                    fa = pending["_fleet_action"]
                    cap          = fa["capability"]
                    filter_type  = fa["filter_type"]
                    filter_value = fa["filter_value"]
                    fa_args      = fa.get("args", {})
                    await self._emit_tool(
                        "[TOOL] fleet_action",
                        f"Confirmed: {cap} → {filter_type}={filter_value or 'all'}",
                    )
                    from backend.app.services.fleet_manager import FleetManager
                    result = await FleetManager().execute_fleet_action(
                        cap, filter_type, filter_value, fa_args, dry_run=False,
                        _intent=getattr(self, "_current_intent", ""),
                    )
                    level = "info" if result["ok"] else "warning"
                    await self._emit_tool("[TOOL] fleet_action", result["summary"], level)
                    return self._simple_response(
                        "Fleet Action Complete" if result["ok"] else "Fleet Action Partial",
                        self._render_fleet_action_result(result),
                    )

                # Capability confirmation
                if "_capability" in pending:
                    cap = pending["_capability"]
                    node_name = pending.get("node", "")
                    cap_args = pending.get("args") or {}
                    await self._emit_tool("[TOOL] execute_capability", f"Confirmed: {cap} → {node_name or 'auto'}")
                    from backend.app.services.capability_executor import CapabilityExecutor
                    executor = CapabilityExecutor()
                    result = await executor.execute(
                        cap, args=cap_args, node_name=node_name or None,
                        _intent=getattr(self, "_current_intent", ""),
                    )
                    level = "info" if result["ok"] else "error"
                    await self._emit_tool("[TOOL] execute_capability", result["summary"], level)
                    return self._node_response(
                        "Capability" if result["ok"] else "Capability Failed",
                        self._render_capability_result(result),
                        result,
                    )
                bulk_type = pending.get("_bulk_type")
                if bulk_type:
                    await self._emit_tool(
                        "[TOOL] send_bulk_command",
                        f"Confirmed bulk: {pending['command']} → all {bulk_type}s",
                    )
                    from backend.app.tools.node_tool import send_bulk_command as _send_bulk
                    result = await _send_bulk(bulk_type, pending["command"], pending.get("payload"))
                    level = "info" if result["ok"] else "warning"
                    await self._emit_tool("[TOOL] send_bulk_command", result["summary"], level)
                    return self._node_response("Bulk Command", self._render_bulk_command_result(result), result)
                else:
                    await self._emit_tool(
                        "[TOOL] send_node_command",
                        f"Confirmed: {pending['command']} → {pending['node']}",
                    )
                    from backend.app.tools.node_tool import send_node_command as _send_cmd
                    result = await _send_cmd(pending["node"], pending["command"], pending.get("payload"))
                    level = "info" if result["ok"] else "error"
                    await self._emit_tool("[TOOL] send_node_command", result["summary"], level)
                    answer = result["summary"] if result["ok"] else f"Command failed: {result.get('error', 'unknown error')}"
                    return self._node_response("Command Sent" if result["ok"] else "Command Failed", answer, result)

        # Soft follow-up offer — "yes" executes it; anything else clears it and
        # flows through normal handling. Never holds destructive actions.
        if self._pending_suggestion:
            suggestion = self._pending_suggestion
            self._pending_suggestion = None
            if _YES_RE.match(raw) and suggestion.get("action") == "telemetry":
                return await self._run_tool("get_node_telemetry", {"node": suggestion["node"]})

        # Statement-intent: "I'm pretty sure nighthawk is online" → verify it
        # now instead of replying with an empty acknowledgement.
        assertion = _NODE_ASSERTION_RE.match(raw)
        if assertion:
            name_guess = assertion.group("node")
            expect_online = assertion.group("state").lower() in ("online", "up", "alive", "reachable")
            from backend.app.tools.node_tool import _find_node, probe_node_by_name
            if _find_node(name_guess) is not None:
                await self._emit_tool("[TOOL] ping_node", f"Verifying claim: {name_guess}")
                loop = __import__("asyncio").get_event_loop()
                result = await loop.run_in_executor(None, probe_node_by_name, name_guess)
                await self._emit_tool("[TOOL] ping_node", result["summary"], "info" if result["ok"] else "warning")
                d = result.get("data") or {}
                node_label = result.get("node") or name_guess
                latency = d.get("latency_ms")
                lat_str = f", responding in {latency:.0f} milliseconds" if latency else ""
                if result["ok"]:
                    lead = "You were right — " if expect_online else "Good news — "
                    answer = f"{lead}{node_label} is online{lat_str}."
                    offer = self._maybe_suggest("probe_telemetry", " Want telemetry as well?")
                    if offer:
                        answer += offer
                        self._pending_suggestion = {"action": "telemetry", "node": node_label}
                else:
                    err = d.get("probe_error") or result.get("error") or "no response to the probe"
                    if expect_online:
                        answer = (
                            f"I checked — {node_label} isn't answering a probe right now ({err}). "
                            f"It could still be up with ICMP blocked; 'verify {node_label}' runs the full chain."
                        )
                    else:
                        answer = f"Confirmed — {node_label} isn't responding ({err})."
                return self._node_response("Node Verified", answer, result)

        # ── Capability self-assessment ────────────────────────────────────────────
        if _CAP_WHAT_CAN_RE.match(raw) or _CAP_LIMITS_RE.match(raw) or _CAP_IMPROVE_RE.search(raw):
            return await self._generate_capability_response(raw, request)

        # ── Projects — deterministic to prevent LLM from inventing project names ──
        if _MY_PROJECTS_RE.search(raw):
            return self._projects_from_brain63_or_registry(raw)

        # ── Entity registry (device/project) — safety net ─────────────────────
        _corr = self._handle_user_correction(raw)
        if _corr is not None:
            return _corr
        _ent = self._handle_entity_query(raw)
        if _ent is not None:
            return _ent

        # ── Timezone preference ──────────────────────────────────────────────────
        tz_set = _TZ_CHANGE_RE.match(raw) or _TZ_USE_RE.match(raw)
        if tz_set:
            loc_raw = tz_set.group("loc").strip()
            iana = resolve_location_to_tz(loc_raw)
            if iana is None:
                answer = (
                    f"I don't recognise '{loc_raw}' as a location. "
                    "Try a city or country name — 'set my timezone to Singapore' or 'use London time'."
                )
                return self._simple_response("Timezone", answer)
            city = tz_display_name(iana)
            set_user_timezone(iana)
            if self.memory_service:
                self.memory_service.remember("user_timezone", iana)
                self.memory_service.remember("user_timezone_label", city)
            answer = f"Got it. I'll use {city} time from now on."
            return self._simple_response("Timezone Set", answer)

        if _TZ_QUERY_RE.match(raw):
            tz_pref = self.memory_service.recall("user_timezone") if self.memory_service else None
            if tz_pref:
                city = tz_display_name(tz_pref)
                time_data = get_time()
                answer = f"You're on {city} time ({tz_pref}). It's {time_data['human']} right now."
            else:
                from backend.config import TIMEZONE as _CFG_TZ
                time_data = get_time()
                answer = (
                    f"No preference set — I'm using the system default ({_CFG_TZ}). "
                    f"It's {time_data['human']} right now. "
                    "Say 'set my timezone to [city]' to change it."
                )
            return self._simple_response("Timezone", answer)

        # ── Diagnostics fast-path ──────────────────────────────────────────
        if re.match(r"^(?:deep\s+system\s+check|(?:run\s+)?(?:silvia\s+)?diagnostics|system\s+(?:health|diagnostics)|health\s+check|check\s+all\s+systems)[\s\.\?!]*$", lowered):
            return await self._run_tool("system_diagnostics", {})

        # ── Reminder management fast-paths ─────────────────────────────────
        m = re.match(r"^(?:dismiss|stop|silence)\s+reminder\s+(.+)$", lowered)
        if m:
            return await self._run_tool("dismiss_reminder", {"query": m.group(1).strip()})
        if re.match(r"^(?:clear|fix|reset)\s+stuck\s+reminders?$", lowered):
            return await self._run_tool("clear_stuck_reminders", {})
        if re.match(r"^(?:pause|mute|stop(?:\s+all)?)\s+reminders?$", lowered):
            return await self._run_tool("pause_reminders", {})
        if re.match(r"^(?:resume|unpause|unmute)\s+reminders?$", lowered):
            return await self._run_tool("resume_reminders", {})
        if re.match(r"^(?:show\s+)?reminder\s+(?:diagnostics|health|status)$", lowered):
            return await self._run_tool("show_reminder_diagnostics", {})

        # Workspace Digital Twin — MUST run before _regex_desktop
        try:
            from backend.app.tools.planner import _regex_workspace as _ws_local
            ws_route = _ws_local(raw)
            if ws_route and ws_route.get("action") == "call_tool":
                return await self._execute_plan(ws_route, request)
        except Exception:
            pass

        # Engineering Planner — MUST run before _regex_desktop
        try:
            from backend.app.tools.planner import _regex_planner as _ep_local
            ep_route = _ep_local(raw)
            if ep_route and ep_route.get("action") == "call_tool":
                return await self._execute_plan(ep_route, request)
        except Exception:
            pass

        # Workflow commands — MUST run before _regex_desktop
        try:
            from backend.app.tools.planner import _regex_workflow as _wf_local
            wf_route = _wf_local(raw)
            if wf_route and wf_route.get("action") == "call_tool":
                return await self._execute_plan(wf_route, request)
        except Exception:
            pass

        # Memory Provider commands — MUST run before _regex_desktop
        try:
            from backend.app.tools.planner import _regex_memory_provider as _mp_local
            mp_route = _mp_local(raw)
            if mp_route and mp_route.get("action") == "call_tool":
                return await self._execute_plan(mp_route, request)
        except Exception:
            pass

        # Brain Steward commands — MUST run before _regex_desktop
        try:
            from backend.app.tools.planner import _regex_brain_steward as _bs_local
            bs_route = _bs_local(raw)
            if bs_route and bs_route.get("action") == "call_tool":
                return await self._execute_plan(bs_route, request)
        except Exception:
            pass

        # System tools — MUST run before _regex_desktop so "run hostname" goes to
        # run_command instead of being treated as an app launch.
        try:
            from backend.app.tools.planner import _regex_system as _sys_re
            sys_route = _sys_re(raw)
            if sys_route and sys_route.get("action") == "call_tool":
                return await self._execute_plan(sys_route, request)
        except Exception:
            pass

        # Internal board router — MUST run before _regex_desktop, which catches all "open X" forms
        try:
            from backend.app.tools.planner import _regex_board as _rb
            board_route = _rb(raw)
            if board_route and board_route.get("action") == "call_tool":
                return await self._execute_plan(board_route, request)
        except Exception:
            pass

        try:
            from backend.app.tools.planner import _regex_desktop
            desktop_route = _regex_desktop(raw)
            if desktop_route and desktop_route.get("action") in ("call_tool", "call_tools"):
                return await self._execute_plan(desktop_route, request)
        except Exception:
            pass

        if self.action_service is not None:
            open_match = re.match(r"^(open|launch|start)\s+(.+)$", raw, flags=re.I)
            if open_match:
                target = open_match.group(2).strip()
                if target.lower().startswith("http://") or target.lower().startswith("https://"):
                    result = self.action_service.open_url(target)
                else:
                    result = self.action_service.execute_alias(target)
                coda = self._tool_coda(target) if result.success else ""
                answer = result.message + coda
                return AssistantResponse(
                    mode="conversation",
                    title="Action",
                    answer=answer,
                    confidence=0.9 if result.success else 0.2,
                    reasoning="Local action command.",
                    processing_time_ms=0,
                    logs=[CommandLogEntry(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        title="Local action",
                        detail=result.message,
                        level="info" if result.success else "error",
                    )],
                    payload={"action_result": result.model_dump(), "speech_text": sanitize_for_speech(answer)},
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

    # ── Engineering Memory handlers (Phase 14C) ──────────────────────────────

    async def _handle_record_memory(self, args: dict) -> AssistantResponse:
        from backend.app.services.project_memory import get_memory, infer_project_from_text, MEMORY_TYPES
        title = args.get("title", "").strip()
        summary = args.get("summary", title).strip()
        mem_type = args.get("type", "").strip().replace(" ", "_")
        project = args.get("project", "").strip()
        reasoning = args.get("reasoning", "").strip()

        if not title:
            return self._simple_response("Record Memory", "No content provided. Try: 'record decision: Use ESP32-C3 for DroneHive FC'")

        if mem_type not in MEMORY_TYPES:
            mem_type = "engineering_note"

        if not project:
            inferred = infer_project_from_text(title + " " + summary)
            project = inferred or "General"

        await self._emit_tool("[TOOL] record_memory", f"{mem_type} → {project}: {title[:60]}")
        mem = get_memory()
        mem_id = mem.record(
            project=project, type=mem_type,
            title=title, summary=summary, reasoning=reasoning,
        )

        type_labels = {
            "decision": "Decision", "lesson": "Lesson Learned", "milestone": "Milestone",
            "failure": "Failure", "success": "Success", "experiment": "Experiment",
            "design_note": "Design Note", "engineering_note": "Engineering Note",
            "risk": "Risk", "assumption": "Assumption", "retrospective": "Retrospective",
        }
        label = type_labels.get(mem_type, mem_type.replace("_", " ").title())

        # Phase 18B: create Brain63 draft workflow for decisions/lessons/milestones
        wf_code = ""
        if mem_type in ("decision", "lesson", "milestone") and project != "General":
            try:
                from backend.app.services.brain_steward import get_brain_steward
                bs = get_brain_steward()
                session_id = getattr(self, "_current_session_id", "")
                if mem_type == "decision":
                    draft = bs.draft_decision(project, title, reason=reasoning or summary)
                elif mem_type == "lesson":
                    draft = bs.draft_lesson(project, title, detail=summary)
                else:
                    draft = bs.draft_milestone(project, title, detail=summary)
                wf = bs.create_draft_workflow(draft, session_id=session_id)
                wf_code = wf.get("code", "")
                await self._emit_tool("[BRAIN63] draft created", f"{wf_code}: {draft['target_file']}", "info")
            except Exception as e:
                logger.debug("Brain63 draft creation failed: %s", e)

        answer = f"**{label} recorded** for **{project}**\n\n> {title}\n\nID: `{mem_id}`  ·  View on **/memory**"
        if wf_code:
            answer += (
                f"\n\nBrain63 draft created: **{wf_code}**\n"
                f"Reply `approve {wf_code}` to commit to Brain63,\n"
                f"or `reject {wf_code}` to skip."
            )
        return self._simple_response(f"{label} Saved", answer)

    async def _handle_get_memory(self, args: dict) -> AssistantResponse:
        from backend.app.services.project_memory import get_memory
        project = args.get("project", "").strip()
        mem_type = args.get("type", "").strip().replace(" ", "_")
        query = args.get("query", "").strip()

        mem = get_memory()
        if not project and not mem_type:
            memories = mem.get_recent(days=30, limit=20)
            header = "Recent Engineering Memories (30 days)"
        elif query:
            memories = mem.search(query, project=project or None)
            header = f"Memory search: '{query}'" + (f" — {project}" if project else "")
        elif project and not mem_type:
            memories = mem.get_project_memories(project, limit=50)
            header = f"Project Memory — {project}"
        else:
            proj_filter = project if project else None
            memories = mem.get_project_memories(proj_filter or "", type=mem_type or None, limit=50)
            type_label = mem_type.replace("_", " ").title() + "s" if mem_type else "Memories"
            header = f"{type_label}" + (f" — {project}" if project else "")

        await self._emit_tool("[TOOL] get_memory", f"{len(memories)} entries")
        return self._simple_response(header, self._render_memory_list(memories, header))

    async def _handle_get_timeline(self, args: dict) -> AssistantResponse:
        from backend.app.services.project_memory import get_memory
        project = args.get("project", "").strip()
        if not project:
            return self._simple_response("Timeline", "Specify a project. Try: 'show timeline Cyberdeck'")
        await self._emit_tool("[TOOL] project_timeline", f"{project}…")
        entries = get_memory().get_timeline(project)
        return self._simple_response(f"Project Timeline — {project}", self._render_timeline(entries, project))

    async def _handle_search_memory(self, args: dict) -> AssistantResponse:
        from backend.app.services.project_memory import get_memory
        query = args.get("query", "").strip()
        project = args.get("project", "").strip()
        if not query:
            return self._simple_response("Memory Search", "Provide a search term.")
        await self._emit_tool("[TOOL] search_memory", f"'{query}'…")
        results = get_memory().search(query, project=project or None)
        if not results:
            return self._simple_response(
                "Memory Search",
                f"No memories found matching '{query}'. Try 'record decision: ...' to add memories.",
            )
        return self._simple_response(f"Memory: '{query}'", self._render_memory_list(results, f"Results for '{query}'"))

    async def _handle_import_memory(self, args: dict) -> AssistantResponse:
        from backend.app.services.project_memory import get_memory
        project = args.get("project", "").strip()
        await self._emit_tool("[TOOL] import_brain63_memory", f"Scanning Brain63 vault{' for ' + project if project else ''}…")
        result = get_memory().import_from_brain63(project=project or None)
        if not result.get("ok"):
            return self._simple_response("Import Failed", f"Brain63 vault not found or inaccessible.")
        imported = result.get("imported", 0)
        errors = result.get("errors", [])
        if imported == 0:
            answer = "No new memories found in Brain63 vault. Either already imported or no matching files (Decisions.md, Lessons_Learned.md, Milestones.md)."
        else:
            answer = f"Imported **{imported}** engineering memories from Brain63 vault."
            if project:
                answer += f"\nProject: **{project}**"
        if errors:
            answer += f"\n\n{len(errors)} file(s) had errors."
        answer += "\n\nView on **/memory**"
        return self._simple_response("Brain63 Import", answer)

    def _render_memory_list(self, memories: list[dict], header: str) -> str:
        if not memories:
            return f"No memories found. Use 'record decision: ...', 'record lesson: ...', etc. to add them."
        type_icons = {
            "decision": "◈", "lesson": "◉", "milestone": "◆",
            "failure": "✗", "success": "✓", "experiment": "⊙",
            "design_note": "◇", "engineering_note": "◎", "risk": "⚠",
            "assumption": "~", "retrospective": "↺",
        }
        type_order = ["milestone", "decision", "lesson", "failure", "success", "risk",
                      "experiment", "design_note", "engineering_note", "assumption", "retrospective"]
        by_type: dict[str, list[dict]] = {}
        for m in memories:
            by_type.setdefault(m["type"], []).append(m)

        lines = [f"**{header}**", f"*{len(memories)} entries*", ""]
        for t in type_order:
            if t not in by_type:
                continue
            icon = type_icons.get(t, "·")
            label = t.replace("_", " ").title() + "s"
            lines.append(f"**{icon} {label}**")
            for m in by_type[t][:8]:
                proj_tag = f" [{m['project']}]" if m.get("project") and m["project"] != "General" else ""
                lines.append(f"  · {m['title']}{proj_tag}  *{m['date']}*")
                if m.get("summary") and m["summary"] != m["title"]:
                    lines.append(f"    {m['summary'][:120]}")
            remaining = len(by_type[t]) - 8
            if remaining > 0:
                lines.append(f"  *…and {remaining} more*")
            lines.append("")

        # Remaining types not in ordered list
        for t, items in by_type.items():
            if t in type_order:
                continue
            icon = type_icons.get(t, "·")
            lines.append(f"**{icon} {t.replace('_', ' ').title()}s**")
            for m in items[:5]:
                lines.append(f"  · {m['title']}  *{m['date']}*")

        lines.append("View full board at **/memory**")
        return "\n".join(lines)

    def _render_timeline(self, entries: list[dict], project: str) -> str:
        if not entries:
            return f"No history recorded for **{project}** yet.\n\nStart with: 'record milestone: {project} project created'"
        type_icons = {
            "decision": "◈", "lesson": "◉", "milestone": "◆",
            "failure": "✗", "success": "✓", "experiment": "⊙",
            "design_note": "◇", "engineering_note": "◎", "risk": "⚠",
            "assumption": "~", "retrospective": "↺",
        }
        lines = [f"**Project Timeline — {project}**", f"*{len(entries)} entries*", ""]
        cur_year_month = ""
        for e in entries:
            date = e.get("date", "")
            ym = date[:7] if date else ""
            if ym != cur_year_month:
                lines.append(f"\n**{ym or 'Unknown date'}**")
                cur_year_month = ym
            icon = type_icons.get(e["type"], "·")
            label = e["type"].replace("_", " ").title()
            lines.append(f"  {icon} {date[8:] or '??'} · **{e['title']}** *({label})*")
        lines.append("\nView full board at **/memory**")
        return "\n".join(lines)

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

    def _render_node_telemetry(self, result: dict) -> str:
        if not result["ok"]:
            return result.get("error") or f"No telemetry found for {result.get('node', 'that node')}."
        d = result["data"]

        # ── All-nodes view ────────────────────────────────────────────────────
        if "nodes" in d:
            nodes = d["nodes"]
            if not nodes:
                return "No nodes in registry."
            # Sort: nodes with temperature first (descending), rest after
            with_temp = sorted(
                [n for n in nodes if n.get("temperature") is not None],
                key=lambda n: n["temperature"],
                reverse=True,
            )
            without_temp = [n for n in nodes if n.get("temperature") is None]
            ordered = with_temp + without_temp
            lines = [f"Infrastructure Telemetry — {len(nodes)} node{'s' if len(nodes) != 1 else ''}\n"]
            for n in ordered:
                status = n["status"].upper()
                metrics = []
                if n.get("cpu") is not None:
                    metrics.append(f"CPU {n['cpu']:.0f}%")
                if n.get("ram") is not None:
                    metrics.append(f"RAM {n['ram']:.0f}%")
                if n.get("disk") is not None:
                    metrics.append(f"Disk {n['disk']:.0f}%")
                if n.get("temperature") is not None:
                    metrics.append(f"{n['temperature']:.0f}°C")
                metric_str = "  " + " · ".join(metrics) if metrics else "  no telemetry"
                lines.append(f"  {n['name']:<20} {status:<10}{metric_str}")
            return "\n".join(lines)

        # ── Single-node view ──────────────────────────────────────────────────
        name = d["name"]
        status = d["status"].capitalize()
        has_metrics = any(d.get(k) is not None for k in ("cpu", "ram", "disk", "temperature"))

        lines = [name.upper(), "", f"Status: {status}"]

        if has_metrics:
            lines.append("")
            if d.get("cpu") is not None:
                lines.append(f"CPU:         {d['cpu']:.0f}%")
            if d.get("ram") is not None:
                lines.append(f"RAM:         {d['ram']:.0f}%")
            if d.get("disk") is not None:
                lines.append(f"Disk:        {d['disk']:.0f}%")
            if d.get("temperature") is not None:
                lines.append(f"Temperature: {d['temperature']:.0f}°C")
            if d.get("uptime") is not None:
                h = d["uptime"] // 3600
                m = (d["uptime"] % 3600) // 60
                lines.append(f"Uptime:      {h}h {m}m")
            # Robotics fields
            if d.get("battery_pct") is not None:
                lines.append(f"Battery:     {d['battery_pct']:.0f}%")
            if d.get("mission_state"):
                lines.append(f"Mission:     {d['mission_state']}")
            if d.get("altitude") is not None:
                lines.append(f"Altitude:    {d['altitude']:.1f}m")
            if d.get("heading") is not None:
                lines.append(f"Heading:     {d['heading']:.0f}°")
            if d.get("position_lat") is not None and d.get("position_lon") is not None:
                lines.append(f"Position:    {d['position_lat']:.6f}, {d['position_lon']:.6f}")
            if d.get("imu_data"):
                imu = d["imu_data"]
                accel_keys = ("accel_x", "accel_y", "accel_z")
                gyro_keys = ("gyro_x", "gyro_y", "gyro_z")
                if any(k in imu for k in accel_keys):
                    ax, ay, az = (imu.get(k, 0) for k in accel_keys)
                    lines.append(f"IMU Accel:   {ax:.2f}/{ay:.2f}/{az:.2f}")
                if any(k in imu for k in gyro_keys):
                    gx, gy, gz = (imu.get(k, 0) for k in gyro_keys)
                    lines.append(f"IMU Gyro:    {gx:.2f}/{gy:.2f}/{gz:.2f}")
        else:
            lines.append("")
            lines.append("No telemetry received yet.")
            if d.get("agent_url"):
                lines.append("Silvia-Agent is configured — telemetry will appear after the next poll (30s).")
            else:
                lines.append("Configure an agent_url on this node to enable live telemetry from Silvia-Agent.")

        lines.append("")
        if d.get("last_seen"):
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(d["last_seen"])
                lines.append(f"Last Seen: {ts.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception:
                lines.append(f"Last Seen: {d['last_seen']}")
        elif d.get("last_probe_at"):
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(d["last_probe_at"])
                lines.append(f"Last Probe: {ts.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception:
                lines.append(f"Last Probe: {d['last_probe_at']}")
        lines.append(f"Source:    {'Silvia-Agent' if d.get('agent_url') else 'Node Probe'}")

        return "\n".join(lines)

    def _render_watch_alerts(self, result: dict) -> str:
        d = result["data"]
        alerts = d["alerts"]
        if not alerts:
            return "Watch Officer: All clear — no active alerts."
        _CAT = {"infra": "OPS", "intel": "INTEL", "mission": "OPS", "system": "SYS", "security": "SEC"}
        count = len(alerts)
        lines = [f"Watch Officer — {count} active alert{'s' if count != 1 else ''}\n"]
        for a in alerts:
            cat = _CAT.get(a["category"], a["category"].upper())
            sev = a["severity"].upper()
            ts = ""
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(a["created_at"])
                ts = f"  {dt.strftime('%H:%M')}"
            except Exception:
                pass
            lines.append(f"  [{cat}] {a['message']}{ts}  ({sev})")
        return "\n".join(lines)

    def _render_node_list_by_type(self, result: dict) -> str:
        d = result["data"]
        nodes = d.get("nodes", [])
        node_type = d.get("type", "node")
        if not nodes:
            return f"No {node_type} nodes registered."
        lines = [f"{node_type.capitalize()} nodes — {len(nodes)}\n"]
        for n in nodes:
            status = n["status"].upper()
            metrics = []
            if n.get("battery_pct") is not None:
                metrics.append(f"Bat {n['battery_pct']:.0f}%")
            if n.get("mission_state"):
                metrics.append(n["mission_state"])
            if n.get("cpu") is not None:
                metrics.append(f"CPU {n['cpu']:.0f}%")
            if n.get("ram") is not None:
                metrics.append(f"RAM {n['ram']:.0f}%")
            metric_str = "  " + " · ".join(metrics) if metrics else ""
            agent_str = "  [agent]" if n.get("agent_url") else ""
            lines.append(f"  {n['name']:<20} {status:<10}{metric_str}{agent_str}")
        return "\n".join(lines)

    def _render_bulk_command_result(self, result: dict) -> str:
        d = result.get("data") or {}
        nodes = d.get("nodes", [])
        succeeded = d.get("succeeded", 0)
        failed = d.get("failed", 0)
        command = d.get("command", "command")
        node_type = d.get("type", "node")
        header = f"Bulk '{command}' on {node_type}s — {succeeded} succeeded, {failed} failed\n"
        lines = [header]
        for n in nodes:
            icon = "✓" if n["ok"] else "✗"
            lines.append(f"  {icon} {n['node']:<20} {n['message']}")
        return "\n".join(lines)

    def _render_services(self, result: dict) -> str:
        d = result.get("data") or {}
        services = d.get("services", [])
        if not services:
            node = d.get("node", "")
            return f"No services registered{' on ' + node if node else ''}."
        lines = []
        current_node = None
        for svc in services:
            node_label = svc.get("node", "")
            if node_label != current_node:
                current_node = node_label
                lines.append(f"\n{node_label}")
                lines.append("─" * 30)
            status = svc.get("status", "unknown")
            transport = svc.get("transport", "http")
            caps = svc.get("capabilities", [])
            cap_str = ", ".join(caps) if caps else "—"
            status_icon = {"running": "●", "stopped": "○", "failed": "✗", "unknown": "?"}.get(status, "?")
            lines.append(f"  {status_icon} {svc['name']:<22} [{transport}] {status}")
            if caps:
                lines.append(f"    capabilities: {cap_str}")
        return "\n".join(lines)

    def _render_capability_result(self, result: dict) -> str:
        d = result.get("data") or {}
        if not result["ok"]:
            error = result.get("error") or result.get("summary", "unknown error")
            cap = d.get("capability") or ""
            svc = d.get("service", "")
            node = d.get("node", "") or result.get("node", "")
            parts = [f"Failed to execute '{cap}'"]
            if node:
                parts.append(f"on {node}")
            if svc:
                parts.append(f"(service: {svc})")
            return f"{' '.join(parts)}: {error}"
        cap = d.get("capability", result.get("tool", ""))
        node = d.get("node", "") or result.get("node", "")
        svc = d.get("service", "")
        output = d.get("output") or d.get("message") or ""
        parts = [f"Executed '{cap}'"]
        if node:
            parts.append(f"on {node}")
        if output:
            parts.append(f"— {output[:200]}")
        return " ".join(parts)

    # ── Fleet renderers (Phase 13B) ───────────────────────────────────────────

    _HEALTH_ICON = {"healthy": "●", "warning": "▲", "critical": "✕", "unknown": "○"}
    _HEALTH_LABEL = {"healthy": "healthy", "warning": "warning", "critical": "critical", "unknown": "unknown"}

    def _render_fleet_status(self, data: dict) -> str:
        score  = data.get("health_score", 0)
        total  = data.get("total", 0)
        online = data.get("online", 0)
        offline = data.get("offline", 0)
        warning = data.get("warning", 0)
        critical = data.get("critical", 0)
        healthy  = data.get("healthy", 0)
        alerts   = data.get("active_alerts", 0)

        bar_fill = int(score / 10) if score > 0 else 0
        bar = "█" * bar_fill + "░" * (10 - bar_fill)
        grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

        lines = [
            f"**Fleet Health — {score}/100** [{bar}] {grade}",
            f"",
            f"● Online {online}/{total}  ✕ Offline {offline}  Active Alerts {alerts}",
            f"",
            f"Nodes: {healthy} healthy · {warning} warning · {critical} critical",
        ]
        if data.get("avg_cpu") is not None:
            lines.append(f"Avg CPU {data['avg_cpu']:.0f}%  RAM {data['avg_ram']:.0f}%  Disk {data['avg_disk']:.0f}%")
        if offline > 0 or warning > 0 or critical > 0:
            lines.append("")
            lines.append("Try **show offline nodes** or **show unhealthy nodes** for details.")
        return "\n".join(lines)

    def _render_fleet_nodes(self, nodes: list[dict], context: str = "") -> str:
        if not nodes:
            verb = "offline" if context == "offline" else "unhealthy"
            return f"No nodes are currently {verb}."
        lines = [f"**{len(nodes)} node(s):**", ""]
        for n in nodes:
            icon = self._HEALTH_ICON.get(n.get("health", "unknown"), "○")
            issues = f" — {', '.join(n['issues'])}" if n.get("issues") else ""
            status = n.get("status", "unknown")
            lines.append(f"{icon} **{n['name']}** ({n['type']}) — {status}{issues}")
        return "\n".join(lines)

    def _render_fleet_groups(self, data: dict) -> str:
        lines = []
        by_type = data.get("by_type", {})
        if by_type:
            lines.append("**By type:**")
            for t, nodes in sorted(by_type.items()):
                names = ", ".join(n["name"] for n in nodes)
                lines.append(f"  {t}: {names}")
        by_tag = data.get("by_tag", {})
        if by_tag:
            lines.append("")
            lines.append("**By tag:**")
            for tag, nodes in sorted(by_tag.items()):
                names = ", ".join(n["name"] for n in nodes)
                lines.append(f"  {tag}: {names}")
        by_svc = data.get("by_service", {})
        if by_svc:
            lines.append("")
            lines.append("**By service:**")
            for svc, nodes in sorted(by_svc.items()):
                names = ", ".join(n["name"] for n in nodes)
                lines.append(f"  {svc}: {names}")
        if not lines:
            return "No nodes registered yet."
        return "\n".join(lines)

    def _render_fleet_action_result(self, result: dict) -> str:
        cap   = result.get("capability", "")
        total = len(result.get("target_nodes", []))
        succ  = result.get("succeeded", 0)
        fail  = result.get("failed", 0)
        lines = [f"**{cap}** — {succ}/{total} succeeded  {fail} failed", ""]
        for r in result.get("results", []):
            icon = "●" if r["ok"] else "✕"
            sim  = " [SIM]" if r.get("simulated") else ""
            lines.append(f"{icon} {r['node']}{sim}: {r['message']}")
        return "\n".join(lines)

    # ── Observability renderers (Phase 13C) ───────────────────────────────────

    def _render_execution_log(self, rows: list[dict]) -> str:
        if not rows:
            return "No execution records found."
        _STATUS_ICON = {"success": "●", "failure": "✕", "simulated": "◎",
                        "dry_run": "◌", "partial": "▲"}
        lines = [f"**{len(rows)} execution(s):**", ""]
        for r in rows:
            ts       = (r.get("ts") or "")[:16].replace("T", " ")
            icon     = _STATUS_ICON.get(r.get("status", ""), "○")
            cap      = r.get("capability") or r.get("tool") or "?"
            node     = r.get("node") or "local"
            dur      = r.get("duration_ms")
            dur_str  = f"  {dur}ms" if dur is not None else ""
            msg      = r.get("message") or ""
            msg_clip = f"  — {msg[:60]}" if msg else ""
            lines.append(f"{icon} [{ts}] **{cap}** on {node}{dur_str}{msg_clip}")
        return "\n".join(lines)

    def _render_failure_log(self, rows: list[dict]) -> str:
        if not rows:
            return "No failures recorded — everything is running cleanly."
        lines = [f"**{len(rows)} failure(s):**", ""]
        for r in rows:
            ts     = (r.get("ts") or "")[:16].replace("T", " ")
            cap    = r.get("capability") or r.get("tool") or "?"
            node   = r.get("node") or "local"
            msg    = r.get("message") or r.get("error") or ""
            intent = r.get("intent") or ""
            lines.append(f"✕ [{ts}] **{cap}** on {node}")
            if intent:
                lines.append(f"    Triggered by: \"{intent}\"")
            if msg:
                lines.append(f"    Error: {msg[:80]}")
        return "\n".join(lines)

    def _render_planner_trace(self, rows: list[dict]) -> str:
        if not rows:
            return "No planner decisions recorded yet."
        lines = [f"**{len(rows)} planner decision(s):**", ""]
        for r in rows:
            ts     = (r.get("ts") or "")[:16].replace("T", " ")
            query  = r.get("query") or "?"
            route  = r.get("route") or "?"
            tool   = r.get("tool") or ""
            conf   = r.get("confidence")
            conf_s = f"  conf={conf:.0%}" if conf is not None else ""
            tool_s = f"  → {tool}" if tool else ""
            lines.append(f"● [{ts}] \"{query[:50]}\"")
            lines.append(f"    route={route}{tool_s}{conf_s}")
        return "\n".join(lines)

    def _render_capability_health(self, data: dict) -> str:
        cap_health  = data.get("capability_health") or []
        node_health = data.get("node_health") or []
        lines = []

        total  = data.get("total_executions", 0)
        succ   = data.get("success_count", 0)
        fail   = data.get("failure_count", 0)
        rate   = f"{data.get('success_rate', 0):.0f}%"
        avg_ms = data.get("avg_duration_ms")
        avg_s  = f"  avg {avg_ms:.0f}ms" if avg_ms else ""
        lines.append(f"**Overall:** {total} executions — {rate} success rate  ({fail} failed){avg_s}")

        if cap_health:
            lines.append("")
            lines.append("**By capability:**")
            for h in sorted(cap_health, key=lambda x: x.get("success_rate", 0)):
                r = h.get("success_rate", 0)     # 0–100
                c = h.get("total", 0)
                cap = h.get("capability", "?")
                icon = "●" if r >= 90 else ("▲" if r >= 50 else "✕")
                lines.append(f"  {icon} {cap}: {r:.0f}%  ({c} calls)")

        if node_health:
            lines.append("")
            lines.append("**By node:**")
            for h in sorted(node_health, key=lambda x: x.get("success_rate", 0)):
                r = h.get("success_rate", 0)     # 0–100
                c = h.get("total", 0)
                node = h.get("node", "?")
                icon = "●" if r >= 90 else ("▲" if r >= 50 else "✕")
                lines.append(f"  {icon} {node}: {r:.0f}%  ({c} executions)")

        return "\n".join(lines) if lines else "No execution data yet."

    # ── Project Intelligence renderers (Phase 14A) ───────────────────────────

    def _render_project_briefing(self, data: dict) -> str:
        name     = data.get("project", "")
        status   = data.get("status", "")
        priority = data.get("priority", "")
        pct      = data.get("readiness_pct", 0)
        bstatus  = data.get("build_status", "no_data")
        parts    = data.get("parts", {})
        missing  = parts.get("missing", [])
        tasks    = data.get("tasks", {})
        blockers = data.get("blockers", [])
        b63ctx   = data.get("brain63_context")
        action   = data.get("recommended_action", "")
        orders   = data.get("orders", [])
        rel_nodes = data.get("related_nodes", [])

        fill  = round(pct / 10)
        bar   = "█" * fill + "░" * (10 - fill)
        lines = [
            f"**{name}** — {status}  ·  {priority} priority",
            f"Readiness: [{bar}] {pct}%  ({bstatus})",
        ]

        if missing:
            lines.append("")
            lines.append(f"**Missing parts ({len(missing)}):**")
            for p in missing[:5]:
                lines.append(f"  ✕ {p['name']} — need {p['quantity_required']}, have {p.get('available_qty', 0)}")
            if len(missing) > 5:
                lines.append(f"  … and {len(missing)-5} more")

        if orders:
            lines.append("")
            lines.append(f"**Pending orders ({len(orders)}):** " + ", ".join(o.get("part_name","") for o in orders[:3]))

        if blockers:
            lines.append("")
            lines.append(f"**Blockers ({len(blockers)}):**")
            for b in blockers[:4]:
                lines.append(f"  ✗ {b['description']}")

        if tasks.get("open", 0) > 0:
            lines.append("")
            lines.append(f"**Open tasks ({tasks['open']}):**")
            for t in (tasks.get("items") or [])[:4]:
                lines.append(f"  • {t.get('title','')}")

        if rel_nodes:
            lines.append("")
            lines.append("**Related nodes:** " + ", ".join(n["name"] for n in rel_nodes[:4]))

        if b63ctx:
            lines.append("")
            lines.append("**Brain63:**")
            for ln in b63ctx.split("\n")[:4]:
                if ln.strip():
                    lines.append(f"  {ln.strip()}")

        # Engineering Memory section
        memory = data.get("memory", {})
        recent_decisions  = memory.get("decisions", [])
        recent_lessons    = memory.get("lessons", [])
        recent_milestones = memory.get("milestones", [])
        known_risks       = memory.get("risks", [])
        recent_failures   = memory.get("failures", [])
        has_memory = any([recent_decisions, recent_lessons, recent_milestones, known_risks, recent_failures])
        if has_memory:
            lines.append("")
            lines.append("**Engineering Memory:**")
            for d in recent_decisions[:2]:
                lines.append(f"  ◈ Decision: {d['title']}")
            for m in recent_milestones[:2]:
                lines.append(f"  ◆ Milestone: {m['title']}")
            for l in recent_lessons[:2]:
                lines.append(f"  ◉ Lesson: {l['title']}")
            for r in known_risks[:2]:
                lines.append(f"  ⚠ Risk: {r['title']}")
            for f in recent_failures[:2]:
                lines.append(f"  ✗ Failure: {f['title']}")

        if action:
            lines.append("")
            lines.append(f"**→ {action}**")

        return "\n".join(lines)

    def _render_project_blockers(self, blockers: list, project: str) -> str:
        if not blockers:
            return f"No blockers found for **{project}**."
        lines = [f"**{len(blockers)} blocker(s) for {project}:**", ""]
        for b in blockers:
            sev = b.get("severity", "")
            icon = "✗" if sev == "high" else "▲"
            lines.append(f"{icon} {b['description']}")
        return "\n".join(lines)

    def _render_pi_projects_list(self, projects: list, context: str = "") -> str:
        if not projects:
            label = context or "matching"
            return f"No projects found {label}."
        lines = [f"**{len(projects)} project(s) {context}:**", ""]
        for p in projects:
            name = p.get("name", "?")
            status = p.get("status", "")
            priority = p.get("priority", "")
            pct = p.get("readiness_pct")
            pct_str = f"  {pct}% ready" if pct is not None else ""
            reason = p.get("reason", "")
            blocking = p.get("blocking_parts", [])
            line = f"  **{name}** — {status} / {priority}{pct_str}"
            if reason:
                line += f"  [{reason}]"
            lines.append(line)
            if blocking:
                lines.append(f"    Missing: {', '.join(blocking[:3])}")
        return "\n".join(lines)

    def _personal_response(self, title: str, answer: str, result: dict) -> AssistantResponse:
        return AssistantResponse(
            mode="conversation",
            title=title,
            answer=answer,
            confidence=0.97,
            reasoning=f"Personal ops tool: {result['tool']}",
            processing_time_ms=0,
            sources=[],
            agents=[AgentStatus(
                name="Personal Ops",
                role="assistant",
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

    def _render_reminder_set(self, result: dict) -> str:
        if not result["ok"]:
            return result.get("error") or result["summary"]
        d = result["data"]
        recurrence = d["recurrence"]
        label = d["when_label"]
        if recurrence == "once":
            return f"Reminder set for {label}: '{d['message']}'"
        return f"Recurring reminder ({label}): '{d['message']}'"

    def _render_reminder_list(self, result: dict) -> str:
        d = result["data"]
        reminders = d["reminders"]
        if not reminders:
            return "No active reminders."
        lines = [f"Reminders — {len(reminders)} active\n"]
        for r in reminders:
            rec = r["recurrence"]
            rec_label = "" if rec == "once" else f"  [{rec.replace('weekly:', 'weekly ').replace('monthly:', 'monthly ')}]"
            lines.append(f"  {r['when_label']}{rec_label}  — {r['message']}")
        return "\n".join(lines)

    def _render_task_list(self, result: dict) -> str:
        d = result["data"]
        tasks = d["tasks"]
        filter_val = d.get("filter", "pending")
        if not tasks:
            label = "pending" if filter_val == "pending" else filter_val
            return f"No {label} tasks."
        # Group by project
        by_project: dict[str, list] = {}
        for t in tasks:
            key = t["project"] or "—"
            by_project.setdefault(key, []).append(t)
        lines = [f"Tasks — {len(tasks)} {filter_val}\n"]
        for proj, proj_tasks in sorted(by_project.items()):
            if len(by_project) > 1:
                lines.append(f"  [{proj}]")
            for t in proj_tasks:
                tick = "✓" if t["status"] == "done" else "·"
                prio = f" ({t['priority']})" if t["priority"] != "normal" else ""
                lines.append(f"    {tick} {t['title']}{prio}")
        return "\n".join(lines)

    def _render_calendar_events(self, result: dict, label: str) -> str:
        d = result["data"]
        events = d["events"]
        if not events:
            return f"No events {label}."
        lines = [f"Calendar — {label} ({len(events)} event{'s' if len(events) != 1 else ''})\n"]
        for e in events:
            try:
                from datetime import datetime
                from backend.app.tools.personal_tool import _utc_to_local, _fmt_datetime_win
                dt = _utc_to_local(e["start_at"])
                time_str = _fmt_datetime_win(dt)
            except Exception:
                time_str = e["start_at"]
            loc = f"  @ {e['location']}" if e.get("location") else ""
            lines.append(f"  {time_str}  {e['title']}{loc}")
        return "\n".join(lines)

    # ── Productivity renderers (Phase 12G) ───────────────────────────────────

    def _render_emails(self, result: dict) -> str:
        if not result["ok"]:
            return result["summary"]
        emails = result["data"].get("emails", [])
        if not emails:
            return "No emails found."
        lines = [f"{result['summary']}\n"]
        for e in emails:
            unread_mark = "●" if e.get("unread") else "○"
            subject = e.get("subject", "(no subject)")
            sender = e.get("sender", "")
            # Simplify sender display — extract just the name
            if "<" in sender:
                sender = sender.split("<")[0].strip().strip('"')
            date = e.get("date", "")[:16] if e.get("date") else ""
            snippet = e.get("snippet", "")[:80]
            lines.append(f"  {unread_mark} **{subject}**")
            lines.append(f"    From: {sender}  |  {date}")
            if snippet:
                lines.append(f"    {snippet}")
        return "\n".join(lines)

    def _render_gcal_events(self, result: dict, period: str) -> str:
        if not result["ok"]:
            return result["summary"]
        events = result["data"].get("events", [])
        if not events:
            return f"No events {period}."
        lines = [f"Google Calendar — {period} ({len(events)} event{'s' if len(events) != 1 else ''})\n"]
        for ev in events:
            start = ev.get("start", "")
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(start)
                start = dt.astimezone().strftime("%a %b %-d at %I:%M%p").replace(" 0", " ").lower()
            except Exception:
                pass
            title = ev.get("title", "(no title)")
            loc = f"  @ {ev['location']}" if ev.get("location") else ""
            lines.append(f"  {start}  **{title}**{loc}")
        return "\n".join(lines)

    def _render_verification(self, result: dict) -> str:
        if not result["ok"]:
            d = result.get("data") or {}
            node = result.get("node", "Node")
            reason = d.get("error") or result.get("error") or "All verification methods failed."
            return f"{node} — unreachable.\n\n{reason}"
        d = result["data"]
        source_labels = {
            "local": "Local machine",
            "silvia-agent": "Silvia-Agent",
            "tailscale": "Tailscale",
            "dns": "DNS resolution",
            "ping": "Direct ping",
        }
        source = source_labels.get(d.get("verification_source", ""), d.get("verification_source", "unknown"))
        lat = d.get("latency_ms")
        lat_str = f" · {lat:.0f}ms" if lat and lat > 0.1 else ""
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(d["last_verified"])
            when = ts.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            when = d.get("last_verified", "now")
        return (
            f"{d['name'].upper()}\n\n"
            f"Status:  Online\n"
            f"Method:  {source}{lat_str}\n"
            f"Verified: {when}\n\n"
            f"Registry updated."
        )

    def _render_refresh(self, result: dict) -> str:
        d = result["data"]
        nodes = d.get("results", [])
        total = d["total"]
        verified_count = d["verified_count"]
        failed_count = d["failed_count"]

        header = f"Node Verification — {verified_count}/{total} online\n"
        lines = [header]
        source_labels = {
            "local": "local",
            "silvia-agent": "agent",
            "tailscale": "tailscale",
            "dns": "dns",
            "ping": "ping",
        }
        for n in nodes:
            status = "ONLINE" if n.get("status") == "online" else "OFFLINE"
            src = source_labels.get(n.get("verification_source", ""), n.get("verification_source") or "—")
            lat = n.get("latency_ms")
            lat_str = f"  {lat:.0f}ms" if lat and lat > 0.1 else ""
            lines.append(f"  {n['name']:<20} {status:<10} via {src}{lat_str}")

        if failed_count:
            lines.append(f"\n{failed_count} node{'s' if failed_count != 1 else ''} unreachable.")
        return "\n".join(lines)

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

    def _render_semantic_results(self, result: dict, query: str) -> str:
        results = result["data"].get("results", [])
        if not results:
            return f"No past conversations found about '{query}'."
        lines = [f"Memory Search — {len(results)} result{'s' if len(results) != 1 else ''} for '{query}'\n"]
        for i, r in enumerate(results, 1):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(r["created_at"])
                when = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                when = r.get("created_at", "")[:16]
            sim_pct = int(r.get("similarity", 0) * 100)
            lines.append(f"  [{i}] {when}  ({sim_pct}% match)")
            lines.append(f"      You: {r['user_msg'][:100]}")
            lines.append(f"      SILVIA: {r['assistant_reply'][:120]}")
        return "\n".join(lines)

    # ── Mission Control renderers ──────────────────────────────────────────────

    def _render_briefing_for_llm(self, data: dict) -> str:
        """Serialize briefing data as readable text for LLM synthesis."""
        lines = [f"OPERATIONAL BRIEFING — {data.get('date', 'Today')}", ""]
        projs = data.get("active_projects", [])
        if projs:
            lines.append("ACTIVE PROJECTS:")
            for p in projs:
                idle = f"  (last active: {p['last_activity']})" if p.get("last_activity") != "unknown" else "  (no recent activity)"
                lines.append(f"  • {p['name']} [{p['priority']}]{idle}")
                if p.get("notes"):
                    lines.append(f"    {p['notes'][:100]}")
        blocked = data.get("blocked_projects", [])
        if blocked:
            lines.append("BLOCKED PROJECTS:")
            for p in blocked:
                lines.append(f"  • {p['name']}: {p.get('notes', '')[:80]}")
        tasks = data.get("high_priority_tasks", [])
        if tasks:
            lines.append(f"\nHIGH PRIORITY TASKS ({data.get('pending_tasks_count', 0)} total pending):")
            for t in tasks:
                proj = f" [{t['project']}]" if t.get("project") else ""
                lines.append(f"  • {t['title']}{proj}")
        elif data.get("pending_tasks_count", 0):
            lines.append(f"\nPENDING TASKS: {data['pending_tasks_count']} tasks pending (none flagged high priority).")
        reminders = data.get("due_reminders", [])
        if reminders:
            lines.append("\nDUE REMINDERS:")
            for r in reminders:
                lines.append(f"  • {r['message']}  (due: {r['trigger_at']})")
        events = data.get("events_today", [])
        if events:
            lines.append("\nTODAY'S CALENDAR:")
            for e in events:
                loc = f" @ {e['location']}" if e.get("location") else ""
                lines.append(f"  • {e['title']} — {e['start_at']}{loc}")
        alerts = data.get("active_alerts", [])
        if alerts:
            lines.append("\nACTIVE ALERTS:")
            for a in alerts:
                lines.append(f"  • [{a['severity'].upper()}] {a['message']}")
        offline = data.get("offline_nodes", [])
        if offline:
            lines.append("\nOFFLINE NODES:")
            for n in offline:
                lines.append(f"  • {n['name']} is offline")
        if not any([projs, blocked, tasks, reminders, events, alerts, offline]):
            lines.append("All clear — no active items requiring attention.")
        return "\n".join(lines)

    def _render_focus_for_llm(self, data: dict) -> str:
        lines = [f"DAILY FOCUS — {data.get('date', 'Today')}", ""]
        items = data.get("items", [])
        if not items:
            lines.append("No specific priorities identified from current data.")
        else:
            lines.append("PRIORITY-RANKED ITEMS:")
            source_labels = {
                "watch_officer": "ALERT",
                "reminder": "REMINDER",
                "task": "TASK",
                "project": "PROJECT",
                "infrastructure": "INFRA",
            }
            for i, item in enumerate(items, 1):
                label = source_labels.get(item["source"], item["source"].upper())
                lines.append(f"  {i}. [{label}] {item['item']}  — {item['action']}")
        lines.append(f"\nContext: {data.get('total_pending_tasks', 0)} pending tasks, "
                     f"{data.get('total_due_reminders', 0)} due reminders, "
                     f"{data.get('active_project_count', 0)} active projects.")
        return "\n".join(lines)

    def _render_weekly_for_llm(self, data: dict) -> str:
        lines = [f"WEEKLY REVIEW — {data.get('period', 'This Week')}", ""]
        completed = data.get("completed_tasks", [])
        if completed:
            lines.append(f"COMPLETED TASKS ({len(completed)}):")
            for t in completed:
                proj = f" [{t['project']}]" if t.get("project") else ""
                lines.append(f"  ✓ {t['title']}{proj}")
        else:
            lines.append("COMPLETED TASKS: None recorded this week.")
        active_week = data.get("active_projects_this_week", [])
        all_active = data.get("all_active_projects", [])
        if active_week:
            lines.append(f"\nPROJECTS WITH ACTIVITY THIS WEEK:")
            for p in active_week:
                lines.append(f"  • {p['name']} [{p['priority']}]")
        elif all_active:
            lines.append(f"\nACTIVE PROJECTS (no recorded activity this week):")
            for p in all_active:
                lines.append(f"  • {p['name']} [{p['status']}]")
        pending = data.get("pending_tasks_count", 0)
        if pending:
            lines.append(f"\nSTILL PENDING: {pending} tasks.")
        events = data.get("upcoming_events", [])
        if events:
            lines.append("\nUPCOMING EVENTS:")
            for e in events:
                lines.append(f"  • {e['title']} — {e['start_at']}")
        reminders = data.get("upcoming_reminders", [])
        if reminders:
            lines.append("\nUPCOMING REMINDERS:")
            for r in reminders:
                lines.append(f"  • {r['message']}  ({r['trigger_at']})")
        alerts = data.get("critical_alerts", [])
        if alerts:
            lines.append(f"\nACTIVE ALERTS ({data.get('active_alerts_count', 0)} total):")
            for a in alerts:
                lines.append(f"  • [{a['severity'].upper()}] {a['message']}")
        return "\n".join(lines)

    def _render_forgotten(self, data: dict) -> str:
        if not data.get("has_anything"):
            return "Nothing appears to be forgotten or overdue. Clean slate."
        lines = []
        stale = data.get("stale_projects", [])
        if stale:
            lines.append(f"**Stale Projects** ({len(stale)} with no recent activity):")
            for p in stale:
                idle = f"{p['idle_days']}d" if p.get("idle_days") is not None else "unknown"
                lines.append(f"  • {p['name']} [{p['status']}] — last activity: {p['last_activity']} ({idle} ago)")
        tasks = data.get("forgotten_tasks", [])
        if tasks:
            lines.append(f"\n**Long-Pending Tasks** ({len(tasks)} tasks older than 7 days):")
            for t in tasks:
                lines.append(f"  • {t['title']} [{t['priority']}] — {t['age_days']}d old")
        reminders = data.get("overdue_reminders", [])
        if reminders:
            lines.append(f"\n**Overdue Reminders** ({len(reminders)} past due):")
            for r in reminders:
                lines.append(f"  • {r['message']}  (due: {r['overdue_since']})")
        alerts = data.get("old_unresolved_alerts", [])
        if alerts:
            lines.append(f"\n**Old Unresolved Alerts** ({len(alerts)} unaddressed):")
            for a in alerts:
                lines.append(f"  • [{a['severity'].upper()}] {a['message']}  ({a['age_days']}d old)")
        return "\n".join(lines) if lines else "Nothing appears to be forgotten."

    def _render_project_health(self, projects: list) -> str:
        if not projects:
            return "No projects found in registry."
        _HEALTH_ICON = {"healthy": "✓", "stale": "~", "blocked": "✗", "no activity": "?"}
        lines = ["Project Health Report", ""]
        for p in projects:
            icon = _HEALTH_ICON.get(p.get("health", "?"), "?")
            tasks_str = f"  {p['pending_tasks']} pending task{'s' if p['pending_tasks'] != 1 else ''}" if p.get("pending_tasks") else ""
            alerts_str = f"  {p['active_alerts']} alert{'s' if p['active_alerts'] != 1 else ''}" if p.get("active_alerts") else ""
            idle_str = f"  idle {p['idle_days']}d" if p.get("idle_days") is not None else "  no activity logged"
            lines.append(f"{icon}  **{p['name']}** [{p['priority']}] {p['status']}")
            lines.append(f"   last active: {p['last_activity']}{idle_str}{tasks_str}{alerts_str}")
            if p.get("task_titles"):
                lines.append(f"   tasks: {', '.join(p['task_titles'][:3])}")
            if p.get("notes"):
                lines.append(f"   {p['notes'][:80]}")
        return "\n".join(lines)

    # ── Workspace Digital Twin renderers (Phase 15A) ─────────────────────────

    def _render_workspace_status(self, data: dict) -> str:
        s = data.get("summary", {})
        lines = [
            "Workspace Summary",
            "",
            f"  Projects: {s.get('total_projects', 0)}  Active: {s.get('active', 0)}  Blocked: {s.get('blocked', 0)}  Ready: {s.get('ready', 0)}",
            f"  Nodes: {s.get('nodes_online', 0)}/{s.get('nodes_total', 0)} online",
            f"  Open Orders: {s.get('open_orders', 0)}  Pending Tasks: {s.get('pending_tasks', 0)}  Alerts: {s.get('active_alerts', 0)}",
            f"  Recent Actions: {s.get('recent_actions', 0)}",
        ]
        top = data.get("priority_project")
        if top:
            lines.append(f"\n  Priority Project: {top['name']} (score {top['score']})")
            lines.append(f"  Recommended: {top['recommended_action']}")
        blocked = data.get("blocked_projects", [])
        if blocked:
            lines.append("\n  Blocked:")
            for b in blocked:
                blockers_str = ", ".join(b["blockers"][:2])
                lines.append(f"    {b['name']} — {blockers_str}")
        ready = data.get("ready_projects", [])
        if ready:
            lines.append("\n  Ready to build:")
            for r in ready:
                lines.append(f"    {r['name']} — {r['readiness_pct']}% ready")
        return "\n".join(lines)

    def _render_workspace_priorities(self, priorities: list) -> str:
        if not priorities:
            return "No active projects to rank."
        lines = [f"Project Priority Ranking ({len(priorities)} projects)", ""]
        for i, p in enumerate(priorities, 1):
            status_str = f"[{p['status']}]" if p["status"] != "active" else ""
            lines.append(f"  {i}. {p['name']} {status_str}".strip())
            lines.append(f"     Score: {p['score']}  Readiness: {p['readiness_pct']}%  Priority: {p['priority']}")
            if p.get("blockers"):
                lines.append(f"     Blockers: {len(p['blockers'])}")
            if p.get("recommended_action"):
                lines.append(f"     → {p['recommended_action']}")
        return "\n".join(lines)

    def _render_daily_briefing(self, data: dict) -> str:
        lines = [data.get("greeting", ""), f"DAILY ENGINEERING BRIEFING — {data.get('date', '')}", ""]
        ws = data.get("workspace", {})
        lines.append(f"WORKSPACE: {ws.get('projects', 0)} projects | {ws.get('active', 0)} active | {ws.get('blocked', 0)} blocked | {ws.get('ready', 0)} ready")
        infra = data.get("infrastructure", {})
        lines.append(f"INFRASTRUCTURE: {infra.get('nodes_online', 0)} nodes online")
        if infra.get("offline_names"):
            lines.append(f"  Offline: {', '.join(infra['offline_names'])}")
        top = data.get("top_priority")
        if top:
            lines.append(f"\nTOP PRIORITY: {top['name']} (score {top['score']}, {top['readiness_pct']}% ready)")
            lines.append(f"  → {top['recommended_action']}")
        prios = data.get("priorities", [])
        if prios:
            lines.append("\nPRIORITY RANKING:")
            for p in prios:
                lines.append(f"  {p['rank']}. {p['name']} — score {p['score']}, {p['readiness_pct']}% ready")
        blocked = data.get("blocked_projects", [])
        if blocked:
            lines.append("\nBLOCKED:")
            for b in blocked:
                lines.append(f"  {b['name']} — {', '.join(b['blockers'][:2])}")
        orders = data.get("pending_orders", [])
        if orders:
            lines.append("\nPENDING ORDERS:")
            for o in orders:
                lines.append(f"  {o['part_name']} [{o['status']}]")
        tasks = data.get("high_priority_tasks", [])
        if tasks:
            lines.append(f"\nHIGH PRIORITY TASKS ({len(tasks)}):")
            for t in tasks:
                proj = f" [{t['project']}]" if t.get("project") else ""
                lines.append(f"  {t['title']}{proj}")
        cal = data.get("calendar_today", [])
        if cal:
            lines.append("\nCALENDAR TODAY:")
            for e in cal:
                lines.append(f"  {e.get('start', '')} — {e.get('title', '')}")
        alerts = data.get("active_alerts", [])
        if alerts:
            lines.append(f"\nACTIVE ALERTS ({len(alerts)}):")
            for a in alerts:
                lines.append(f"  [{a['severity'].upper()}] {a['message']}")
        changes = data.get("recent_changes", [])
        if changes:
            lines.append("\nRECENT CHANGES:")
            for c in changes:
                lines.append(f"  {c.get('intent', '')} — {c.get('message', '')}")
        memories = data.get("recent_memories", [])
        if memories:
            lines.append("\nRECENT MEMORIES:")
            for m in memories:
                lines.append(f"  [{m['type']}] {m['title']} ({m['project']})")
        return "\n".join(lines)

    def _render_blocked_projects(self, blocked: list) -> str:
        if not blocked:
            return "No projects are currently blocked."
        lines = [f"{len(blocked)} Blocked Project{'s' if len(blocked) != 1 else ''}", ""]
        for p in blocked:
            lines.append(f"  {p['name']} [{p['priority']}]")
            for b in p.get("blockers", []):
                lines.append(f"    — {b['description']}")
        return "\n".join(lines)

    def _render_work_recommendation(self, result: dict) -> str:
        rec = result.get("recommendation")
        if not rec:
            return "No active projects to recommend."
        lines = [
            f"RECOMMENDED PROJECT: {rec['project']}",
            f"Score: {rec['score']}  Readiness: {rec['readiness_pct']}%",
            "",
            "REASONS:",
        ]
        for r in rec.get("reasons", []):
            lines.append(f"  • {r}")
        tasks = rec.get("suggested_tasks", [])
        if tasks:
            lines.append("\nSUGGESTED TASKS:")
            for i, t in enumerate(tasks, 1):
                lines.append(f"  {i}. {t}")
        if rec.get("recommended_action"):
            lines.append(f"\n→ {rec['recommended_action']}")
        alts = result.get("alternatives", [])
        if alts:
            lines.append("\nALTERNATIVES:")
            for a in alts:
                lines.append(f"  {a['project']} — score {a['score']}, {a['readiness_pct']}% ready")
        return "\n".join(lines)

    def _render_reconciled_orders(self, data: dict) -> str:
        sources = data.get("sources_used", [])
        source_str = ", ".join(sources) if sources else "project_registry"
        lines = [
            f"Digital Twin — {data['project']}",
            f"Sources: {source_str}",
            "",
        ]
        buy_now = data.get("buy_now", [])
        buy_soon = data.get("buy_soon", [])
        owned = data.get("already_owned", [])
        ordered = data.get("already_ordered", [])
        stale = data.get("stale_entries", [])
        if buy_now:
            lines.append(f"BUY NOW ({len(buy_now)}):")
            for item in buy_now:
                lines.append(f"  • {item['name']}")
        if buy_soon:
            lines.append(f"\nBUY SOON ({len(buy_soon)}):")
            for item in buy_soon:
                phase = f" [{item.get('phase', '')}]" if item.get("phase") else ""
                lines.append(f"  • {item['name']}{phase}")
        if ordered:
            lines.append(f"\nALREADY ORDERED ({len(ordered)}):")
            for item in ordered:
                lines.append(f"  • {item['name']}")
        if owned:
            lines.append(f"\nALREADY OWNED ({len(owned)}):")
            for item in owned:
                lines.append(f"  • {item['name']}")
        if stale:
            lines.append(f"\nSTALE BRAIN63 ENTRIES ({len(stale)}):")
            for item in stale:
                note = item.get("stale_note", "Brain63 reference may be outdated.")
                lines.append(f"  • {item['name']} — {note}")
        if not buy_now and not buy_soon:
            lines.append("\nNo items to order — everything is owned or on order.")
        return "\n".join(lines)

    # ── Engineering Planner renderers (Phase 15B) ───────────────────────────

    def _render_project_design(self, result: dict) -> str:
        name = result.get("project_name", "")
        lines = [f"Project Design — {name}"]
        if result.get("description"):
            lines.append(result["description"])
        lines.append("")
        diff = result.get("difficulty", "unknown")
        tags = ", ".join(result.get("tags", []))
        lines.append(f"Difficulty: {diff}  |  Tags: {tags or 'none'}")

        arch = result.get("architecture", {})
        if arch:
            lines.append(f"\nArchitecture:")
            if arch.get("purpose"):
                lines.append(f"  Purpose: {arch['purpose']}")
            comps = arch.get("components", [])
            if comps:
                lines.append(f"  Components: {', '.join(str(c) for c in comps[:8])}")
            if arch.get("connections"):
                lines.append(f"  Connections: {arch['connections']}")

        bom = result.get("bom", {})
        if bom and bom.get("total"):
            lines.append(f"\nBOM: {bom['total']} parts, {bom.get('available', 0)} available, {bom.get('missing', 0)} missing ({bom.get('readiness_pct', 0)}% ready)")

        gap = result.get("gap", {})
        if gap.get("missing"):
            lines.append(f"\nMissing ({len(gap['missing'])}):")
            for m in gap["missing"][:8]:
                cname = m.get("component", m) if isinstance(m, dict) else m
                lines.append(f"  • {cname}")

        phases = result.get("phases", [])
        if phases:
            lines.append(f"\nPhases ({len(phases)}):")
            for p in phases:
                pname = p.get("name", p) if isinstance(p, dict) else p
                items = p.get("items", []) if isinstance(p, dict) else []
                lines.append(f"  {pname}: {len(items)} items")

        if result.get("note"):
            lines.append(f"\n{result['note']}")
        return "\n".join(lines)

    def _render_bom(self, result: dict) -> str:
        lines = [f"Bill of Materials — {result['project']}", f"Source: {result.get('source', 'unknown')}", ""]
        lines.append(f"Total: {result['total']}  |  Available: {result['available']}  |  Missing: {result['missing']}  |  Readiness: {result.get('readiness_pct', 0)}%")
        lines.append("")
        for item in result.get("bom", []):
            status = "✓" if item.get("available") else "✗"
            phase = f" [{item.get('phase', '')}]" if item.get("phase") else ""
            lines.append(f"  {status} {item['component']}{phase}")
        return "\n".join(lines)

    def _bom_rich_payload(self, result: dict) -> dict:
        headers = ["Status", "Component", "Qty", "Phase"]
        rows = []
        for item in result.get("bom", []):
            rows.append([
                "Owned" if item.get("available") else "Missing",
                item["component"],
                str(item.get("qty", 1)),
                item.get("phase", ""),
            ])
        return {
            "type": "table",
            "title": f"BOM — {result['project']}",
            "headers": headers,
            "rows": rows,
            "chart_data": {
                "available": result.get("available", 0),
                "missing": result.get("missing", 0),
                "total": result.get("total", 0),
                "readiness_pct": result.get("readiness_pct", 0),
            },
        }

    def _render_planner_roadmap(self, result: dict) -> str:
        lines = [f"Roadmap — {result['project']}", f"Source: {result.get('source', 'unknown')}", ""]
        for phase in result.get("phases", []):
            done = phase.get("done", 0)
            total = phase.get("total", 0)
            pct = round(done / total * 100) if total else 0
            lines.append(f"  {phase['name']} — {pct}% ({done}/{total})")
            for item in phase.get("items", []):
                check = "✓" if item.get("checked") else "○"
                lines.append(f"    {check} {item['name']}")
        return "\n".join(lines)

    def _roadmap_rich_payload(self, result: dict) -> dict:
        phases = []
        for phase in result.get("phases", []):
            phases.append({
                "phase": phase["name"],
                "done": phase.get("done", 0),
                "total": phase.get("total", 0),
                "items": [{"name": i["name"], "checked": i.get("checked", False)} for i in phase.get("items", [])],
            })
        return {
            "type": "checklist",
            "title": f"Roadmap — {result['project']}",
            "phases": phases,
        }

    def _render_gap_analysis(self, result: dict) -> str:
        lines = [result.get("summary", ""), ""]
        owned = result.get("owned", [])
        missing = result.get("missing", [])
        if owned:
            lines.append(f"OWNED ({len(owned)}):")
            for item in owned[:10]:
                lines.append(f"  ✓ {item['component']}")
        if missing:
            lines.append(f"\nMISSING ({len(missing)}):")
            for item in missing[:10]:
                lines.append(f"  ✗ {item['component']}")
        return "\n".join(lines)

    def _render_what_can_i_build(self, result: dict) -> str:
        lines = [result.get("summary", ""), ""]
        suggestions = result.get("suggestions", [])
        if suggestions:
            lines.append("Template Matches:")
            for s in suggestions:
                lines.append(f"  {s['name']} — {s['match_pct']}% match ({s['difficulty']}) | {len(s.get('matched_items', []))} matched, {len(s.get('missing_items', []))} missing")
        custom = result.get("custom_ideas", [])
        if custom:
            lines.append("\nCustom Ideas:")
            for c in custom:
                lines.append(f"  {c['name']} ({c['difficulty']}) — {c['reason']}")
        if not suggestions and not custom:
            lines.append("No project suggestions. Add parts to the Hardware Board to enable inventory-aware planning.")
        return "\n".join(lines)

    def _render_architecture(self, result: dict) -> str:
        arch = result.get("architecture", {})
        lines = [f"Architecture — {result.get('project', '')}", ""]
        if arch.get("purpose"):
            lines.append(f"Purpose: {arch['purpose']}")
        comps = arch.get("components", [])
        if comps:
            lines.append(f"\nComponents ({len(comps)}):")
            for c in comps[:12]:
                lines.append(f"  • {c}")
        if arch.get("connections"):
            lines.append(f"\nConnections: {arch['connections']}")
        if arch.get("firmware"):
            lines.append(f"\nFirmware/Software:")
            for f in arch["firmware"]:
                lines.append(f"  • {f}")
        deps = arch.get("dependencies", [])
        if deps:
            lines.append(f"\nDependencies: {', '.join(deps)}")
        nodes = arch.get("related_nodes", [])
        if nodes:
            lines.append(f"Related Nodes: {', '.join(nodes)}")
        if result.get("difficulty") and result["difficulty"] != "unknown":
            lines.append(f"\nDifficulty: {result['difficulty']}")
        return "\n".join(lines)

    def _render_procurement_plan(self, result: dict) -> str:
        lines = [result.get("summary", ""), ""]
        buy_now = result.get("buy_now", [])
        buy_soon = result.get("buy_soon", [])
        optional = result.get("optional", [])
        if buy_now:
            lines.append(f"BUY NOW ({len(buy_now)}):")
            for item in buy_now:
                lines.append(f"  • {item['component']}")
        if buy_soon:
            lines.append(f"\nBUY SOON ({len(buy_soon)}):")
            for item in buy_soon:
                lines.append(f"  • {item['component']}")
        if optional:
            lines.append(f"\nOPTIONAL ({len(optional)}):")
            for item in optional:
                lines.append(f"  • {item['component']}")
        if not buy_now and not buy_soon and not optional:
            lines.append("Nothing to buy — all parts are accounted for.")
        return "\n".join(lines)

    def _render_templates(self, templates: list) -> str:
        lines = [f"Available Project Templates ({len(templates)}):", ""]
        for t in templates:
            lines.append(f"  {t['name']} ({t['difficulty']}) — {t['description']}")
            lines.append(f"    {t['phase_count']} phases, {t['total_items']} items  |  Tags: {', '.join(t['tags'])}")
        return "\n".join(lines)

    # ── Screen Awareness renderer (Phase 16A) ─────────────────────────────

    # ── Safety / Approval renderers (Phase 17A) ────────────────────────────

    def _render_approval_card(self, approval: dict) -> AssistantResponse:
        """Render an approval request card."""
        risk_labels = {"read": "Read", "low": "Low", "moderate": "Moderate", "high": "High", "critical": "Critical"}
        risk_name = approval.get("risk_name", "unknown")
        risk_display = risk_labels.get(risk_name, risk_name.title())
        tool = approval.get("tool_name", "unknown")
        code = approval.get("code", "???")
        reason = approval.get("reason", "")
        args = approval.get("args", {})
        expires = approval.get("expires_at", "")[:16].replace("T", " ")

        target = args.get("node", args.get("project", args.get("name", args.get("query", ""))))

        lines = [
            f"This action requires approval.",
            "",
            f"Action: {tool.replace('_', ' ').title()}",
        ]
        if target:
            lines.append(f"Target: {target}")
        lines.append(f"Risk: {risk_display}")
        if reason:
            lines.append(f"Reason: {reason}")
        lines.append(f"Expires: {expires} UTC")
        lines.append(f"Approval code: {code}")
        lines.append("")
        lines.append(f"Reply: approve {code}")
        lines.append(f"   or: reject {code}")

        return AssistantResponse(
            mode="conversation",
            answer="\n".join(lines),
            title=f"Approval Required — {code}",
            processing_time_ms=0,
            payload={
                "approval": {
                    "code": code,
                    "tool": tool,
                    "target": target or "",
                    "risk": risk_display,
                    "reason": reason,
                    "expires": expires,
                    "status": "pending",
                },
            },
        )

    def _render_workflow_list(self, workflows: list[dict], title: str = "Workflows") -> str:
        """Render a list of workflows."""
        if not workflows:
            return f"No {title.lower()} found."

        status_icons = {
            "draft": "○", "pending_review": "◐", "approved": "●",
            "rejected": "✗", "executing": "⟳", "completed": "✓",
            "failed": "✗", "cancelled": "—",
        }

        lines = [f"{title} ({len(workflows)}):", ""]
        for wf in workflows:
            icon = status_icons.get(wf.get("status", ""), "?")
            code = wf.get("code", "?")
            status = wf.get("status", "?").replace("_", " ").title()
            wf_title = wf.get("title", "")
            risk = wf.get("risk_level", "").title()
            cat = wf.get("category", "").replace("_", " ").title()
            created = wf.get("created_at", "")[:16].replace("T", " ")
            lines.append(f"  {icon} {code}  {wf_title}")
            lines.append(f"    Status: {status} · Risk: {risk} · Category: {cat}")
            lines.append(f"    Created: {created}")
            lines.append("")

        pending_count = sum(1 for w in workflows if w.get("status") == "pending_review")
        if pending_count:
            lines.append(f"{pending_count} workflow(s) awaiting review.")
        return "\n".join(lines)

    def _render_workflow_detail(self, wf: dict) -> str:
        """Render detailed view of a single workflow."""
        status_labels = {
            "draft": "Draft", "pending_review": "Pending Review",
            "approved": "Approved", "rejected": "Rejected",
            "executing": "Executing", "completed": "Completed",
            "failed": "Failed", "cancelled": "Cancelled",
        }

        code = wf.get("code", "?")
        title = wf.get("title", "")
        status = status_labels.get(wf.get("status", ""), wf.get("status", ""))
        risk = wf.get("risk_level", "").title()
        category = wf.get("category", "").replace("_", " ").title()
        description = wf.get("description", "")
        diff = wf.get("diff_text", "")
        tool = wf.get("tool_name", "")
        created = wf.get("created_at", "")[:16].replace("T", " ")
        resolved = wf.get("resolved_at", "")
        if resolved:
            resolved = resolved[:16].replace("T", " ")
        executed = wf.get("executed_at", "")
        if executed:
            executed = executed[:16].replace("T", " ")
        result = wf.get("execution_result", "")
        affected = wf.get("affected", [])
        affected_str = ", ".join(a for a in affected if a) if isinstance(affected, list) else str(affected)
        project = wf.get("project", "")

        lines = [
            f"Workflow {code}: {title}",
            "",
            f"Status: {status}",
            f"Risk: {risk}",
            f"Category: {category}",
        ]
        if project:
            lines.append(f"Project: {project}")
        if affected_str:
            lines.append(f"Affected: {affected_str}")
        if tool:
            lines.append(f"Tool: {tool}")
        lines.append(f"Created: {created}")
        if resolved:
            lines.append(f"Resolved: {resolved}")
        if executed:
            lines.append(f"Executed: {executed}")

        if description:
            lines.append("")
            lines.append("Details:")
            lines.append(description)

        if diff:
            lines.append("")
            lines.append("Changes:")
            lines.append(diff)

        if result:
            lines.append("")
            lines.append(f"Result: {result}")

        if wf.get("status") == "pending_review":
            lines.append("")
            lines.append(f"Reply: approve {code}")
            lines.append(f"   or: reject {code}")

        return "\n".join(lines)

    # ── Brain63 Steward renderers (Phase 18B) ──────────────────────────────

    def _render_brain63_health(self, health: dict) -> str:
        if not health.get("available"):
            return f"Brain63 vault unavailable: {health.get('error', 'not found')}"

        projects = health.get("projects", [])
        total = health.get("total_projects", 0)
        coverage = health.get("overall_coverage", 0)
        missing = health.get("total_missing", 0)

        lines = [f"Brain63 Health: {coverage}% coverage across {total} projects", ""]

        needs_update = [p for p in projects if p["coverage"] < 100]
        fully_doc = [p for p in projects if p["coverage"] == 100]

        if needs_update:
            lines.append(f"Needs updates ({len(needs_update)}):")
            for p in needs_update:
                lines.append(f"  {p['name']}: {p['coverage']}% — missing: {', '.join(p['missing'])}")
            lines.append("")

        if fully_doc:
            lines.append(f"Fully documented ({len(fully_doc)}):")
            for p in fully_doc:
                lines.append(f"  ✓ {p['name']}")

        return "\n".join(lines)

    def _render_brain63_coverage(self, data: dict) -> str:
        if data.get("error"):
            return data["error"]

        if "project" in data:
            p = data["project"]
            lines = [
                f"Documentation Coverage: {p['name']}",
                f"Coverage: {p['coverage']}%",
                f"Files: {', '.join(p['files'])}",
            ]
            if p.get("missing"):
                lines.append(f"Missing: {', '.join(p['missing'])}")
            return "\n".join(lines)

        return self._render_brain63_health(data)

    def _render_brain63_drafts(self, drafts: list[dict]) -> str:
        if not drafts:
            return "No pending Brain63 drafts."
        lines = [f"Pending Brain63 Drafts ({len(drafts)}):", ""]
        for d in drafts:
            code = d.get("code", "?")
            title = d.get("title", "")
            lines.append(f"  {code}: {title}")
            if d.get("description"):
                lines.append(f"    {d['description'][:100]}")
            lines.append("")
        return "\n".join(lines)

    # ── Memory Provider renderers (Phase 18A) ─────────────────────────────

    def _render_memory_providers(self, providers: list[dict]) -> str:
        if not providers:
            return "No memory providers configured."
        lines = [f"Memory Providers ({len(providers)}):", ""]
        for p in providers:
            icon = "✓" if p.get("available") else "✗"
            lines.append(f"  {icon} {p['name']}")
            lines.append(f"    Entries: {p.get('entry_count', 0)} · Priority: {p.get('priority', '—')}")
            if p.get("details"):
                lines.append(f"    {p['details']}")
            lines.append("")
        return "\n".join(lines)

    def _render_memory_health(self, health: dict) -> str:
        providers = health.get("providers", [])
        total = health.get("total_providers", 0)
        available = health.get("available_providers", 0)
        entries = health.get("total_entries", 0)

        lines = [
            f"Memory Health: {available}/{total} providers online, {entries} total entries",
            "",
        ]
        for p in providers:
            icon = "✓" if p.get("available") else "✗"
            lines.append(f"  {icon} {p['name']}: {p.get('entry_count', 0)} entries")
            if p.get("details"):
                lines.append(f"    {p['details']}")
        return "\n".join(lines)

    def _render_memory_timeline(self, entries: list, project: str = "") -> str:
        if not entries:
            label = f" for {project}" if project else ""
            return f"No timeline entries found{label}."

        label = f" — {project}" if project else ""
        lines = [f"Memory Timeline{label} ({len(entries)} entries):", ""]
        for entry in entries:
            date = (entry.date[:10] if hasattr(entry, 'date') else entry.get("date", "")[:10]) or "——"
            provider = entry.provider if hasattr(entry, 'provider') else entry.get("provider", "")
            etype = entry.type if hasattr(entry, 'type') else entry.get("type", "")
            title = entry.title if hasattr(entry, 'title') else entry.get("title", "")
            lines.append(f"  {date}  [{provider}] {etype}: {title}")
        return "\n".join(lines)

    def _render_memory_relationships(self, rels: list[dict]) -> str:
        if not rels:
            return "No relationships found."
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            name_cache: dict[str, str] = {}
            def _name(eid: str) -> str:
                if eid not in name_cache:
                    e = kg.get_entity(eid)
                    name_cache[eid] = e.get("name", eid[:12]) if e else eid[:12]
                return name_cache[eid]
        except Exception:
            def _name(eid: str) -> str:
                return eid[:12]

        lines = [f"Relationships ({len(rels)}):", ""]
        for r in rels:
            from_name = _name(r.get("from_id", ""))
            to_name = _name(r.get("to_id", ""))
            rel_type = r.get("rel_type", "")
            lines.append(f"  {from_name} —[{rel_type}]→ {to_name}")
        return "\n".join(lines)

    def _render_memory_search(self, entries: list, query: str = "") -> str:
        if not entries:
            return f"No results found for '{query}'." if query else "No results."
        lines = [f"Search results for '{query}' ({len(entries)}):", ""]
        for entry in entries:
            provider = entry.provider if hasattr(entry, 'provider') else entry.get("provider", "")
            title = entry.title if hasattr(entry, 'title') else entry.get("title", "")
            content = entry.content if hasattr(entry, 'content') else entry.get("content", "")
            project = entry.project if hasattr(entry, 'project') else entry.get("project", "")
            score = entry.score if hasattr(entry, 'score') else entry.get("score", 0)

            proj_tag = f" [{project}]" if project else ""
            lines.append(f"  [{provider}]{proj_tag} {title}")
            if content:
                lines.append(f"    {content[:150]}")
            lines.append("")
        return "\n".join(lines)

    def _render_workspace_context(self, ctx: dict) -> str:
        lines = []
        session = ctx.get("session_type", "")
        if session:
            lines.append(f"Session: {session}")

        app = ctx.get("active_app", "")
        if app:
            lines.append(f"Active App: {app}")

        project = ctx.get("project", "")
        if project:
            lines.append(f"Project: {project}")

        file_ = ctx.get("file", "")
        if file_:
            lines.append(f"File: {file_}")

        workspace = ctx.get("workspace", "")
        if workspace and workspace != project:
            lines.append(f"Workspace: {workspace}")

        eng = ctx.get("engineering_context", {})
        if eng.get("language"):
            lines.append(f"Language: {eng['language']}")
        if eng.get("site"):
            lines.append(f"Site: {eng['site']}")
        if eng.get("activity"):
            lines.append(f"Activity: {eng['activity']}")
        if eng.get("kicad_tool"):
            lines.append(f"KiCad Tool: {eng['kicad_tool']}")

        tools = ctx.get("open_tools", [])
        if tools:
            tool_names = [t["app_name"] for t in tools]
            lines.append(f"\nOpen Engineering Tools ({len(tools)}):")
            for t in tools:
                lines.append(f"  {t['app_name']} [{t['category']}]")

        summary = ctx.get("tool_summary", "")
        if not lines:
            return "No active engineering context detected. Open an engineering tool to enable screen awareness."

        return "\n".join(lines)

    # ── Session Continuity renderers (Phase 16B) ──────────────────────────

    def _render_sessions(self, sessions: list) -> str:
        if not sessions:
            return "No sessions recorded yet. Work in an engineering tool to build session history."
        lines = [f"Recent Sessions ({len(sessions)}):", ""]
        for s in sessions:
            proj = s.get("project", "unknown")
            dur = s.get("duration_minutes", 0)
            stype = s.get("session_type", "")
            started = s.get("started_at", "")[:16].replace("T", " ")
            apps = ", ".join(s.get("apps", [])[:3])
            lines.append(f"  {started}  {proj} ({dur}m) [{stype}]")
            if apps:
                lines.append(f"    Apps: {apps}")
            files = s.get("files", [])
            if files:
                lines.append(f"    Files: {', '.join(files[:3])}")
        return "\n".join(lines)

    def _render_single_session(self, s: dict) -> str:
        lines = [f"Last Session — {s.get('project', 'unknown')}", ""]
        lines.append(f"Started: {s.get('started_at', '')[:16].replace('T', ' ')}")
        lines.append(f"Duration: {s.get('duration_minutes', 0)} minutes")
        lines.append(f"Session type: {s.get('session_type', 'unknown')}")
        apps = s.get("apps", [])
        if apps:
            lines.append(f"Applications: {', '.join(apps)}")
        files = s.get("files", [])
        if files:
            lines.append(f"Files: {', '.join(files)}")
        if s.get("summary"):
            lines.append(f"\n{s['summary']}")
        return "\n".join(lines)

    def _render_continue_project(self, result: dict) -> str:
        lines = [f"Project: {result['project']}", ""]
        lines.append(f"Status: {result.get('status', 'unknown')}  |  Priority: {result.get('priority', 'normal')}  |  Readiness: {result.get('readiness_pct', 0)}%")

        last = result.get("last_session")
        if last and last.get("when"):
            lines.append(f"\nLast session: {last['when'][:16].replace('T', ' ')} ({last.get('duration', 0)}m)")
            if last.get("session_type"):
                lines.append(f"  Type: {last['session_type']}")
            if last.get("files"):
                lines.append(f"  Files: {', '.join(last['files'][:3])}")
            if last.get("apps"):
                lines.append(f"  Apps: {', '.join(last['apps'][:3])}")
        else:
            lines.append("\nNo previous session recorded for this project.")

        tasks = result.get("open_tasks", [])
        if tasks:
            lines.append(f"\nOpen tasks ({len(tasks)}):")
            for t in tasks:
                lines.append(f"  • {t}")

        memory = result.get("recent_memory", [])
        if memory:
            lines.append(f"\nRecent memory:")
            for m in memory[:3]:
                lines.append(f"  [{m.get('type', '')}] {m.get('title', '')}")

        rec = result.get("recommended_action", "")
        if rec:
            lines.append(f"\nRecommended next: {rec}")

        return "\n".join(lines)

    def _render_accomplishments(self, result: dict) -> str:
        lines = [result.get("summary", "No activity."), ""]
        for p in result.get("projects", []):
            proj_name = p.get("project", "")
            mins = p.get("minutes", 0)
            sess = p.get("sessions", p.get("entries", 0))
            apps_str = ", ".join(p.get("apps", [])) if isinstance(p.get("apps"), list) else p.get("apps", "")
            lines.append(f"  {proj_name} — {sess} session(s), ~{mins}m")
            if apps_str:
                lines.append(f"    via {apps_str}")
            files = p.get("files", [])
            if files:
                lines.append(f"    Files: {', '.join(files[:3])}")

        milestones = result.get("milestones", [])
        if milestones:
            lines.append("\nRecent milestones:")
            for m in milestones[:3]:
                lines.append(f"  • {m.get('title', '')}")
        return "\n".join(lines)

    def _render_evening_for_llm(self, data: dict) -> str:
        lines = [f"EVENING REVIEW — {data.get('date', 'Today')}", ""]
        totals = data.get("totals", {})
        completed = data.get("completed_tasks_today", [])
        if completed:
            lines.append(f"COMPLETED TODAY ({len(completed)}):")
            for t in completed:
                proj = f" [{t['project']}]" if t.get("project") else ""
                lines.append(f"  ✓ {t['title']}{proj}")
        else:
            lines.append("COMPLETED TODAY: No tasks marked done today.")
        active = data.get("projects_active_today", [])
        if active:
            lines.append(f"\nPROJECTS TOUCHED TODAY:")
            for p in active:
                lines.append(f"  • {p['name']} [{p['status']}]")
        alerts = data.get("alerts_today", [])
        if alerts:
            lines.append(f"\nALERTS GENERATED TODAY ({len(alerts)}):")
            for a in alerts[:5]:
                lines.append(f"  • [{a['severity'].upper()}] {a['message']}")
        outstanding = data.get("outstanding", {})
        pending = outstanding.get("pending_tasks", 0)
        high = outstanding.get("high_priority_tasks", [])
        overdue = outstanding.get("overdue_reminders", [])
        offline = outstanding.get("offline_nodes", [])
        if pending or overdue or offline:
            lines.append(f"\nOUTSTANDING:")
            if high:
                lines.append(f"  High-priority tasks ({len(high)}):")
                for t in high:
                    proj = f" [{t['project']}]" if t.get("project") else ""
                    lines.append(f"    • {t['title']}{proj}")
            elif pending:
                lines.append(f"  {pending} pending task(s) remain.")
            for r in overdue:
                lines.append(f"  • OVERDUE REMINDER: {r['message']} (since {r['overdue_since']})")
            for n in offline:
                lines.append(f"  • OFFLINE NODE: {n['name']}")
        if not any([completed, active, alerts, pending, overdue, offline]):
            lines.append("Quiet day — no significant activity recorded.")
        return "\n".join(lines)

    def _render_projects_list(self, projects: list) -> str:
        if not projects:
            return "No projects registered."
        _STATUS_ICON = {"active": "◉", "paused": "◎", "complete": "✓", "blocked": "✗"}
        _PRI = {"critical": "[!!]", "high": "[!]", "normal": "", "low": "[low]"}
        lines = []
        by_status: dict[str, list] = {}
        for p in projects:
            by_status.setdefault(p.get("status", "unknown"), []).append(p)
        order = ["active", "blocked", "paused", "complete"]
        for status in order:
            bucket = by_status.get(status, [])
            if not bucket:
                continue
            lines.append(f"**{status.capitalize()}**")
            for p in bucket:
                icon = _STATUS_ICON.get(status, "·")
                pri = _PRI.get(p.get("priority", "normal"), "")
                notes = f"  — {p['notes'][:60]}" if p.get("notes") else ""
                b63 = f"  [Brain63: {p['brain63_key']}]" if p.get("brain63_key") else ""
                lines.append(f"  {icon} {p['name']}{' ' + pri if pri else ''}{b63}{notes}")
        return "\n".join(lines)

    async def _call_llm(self, messages: list[dict], max_tokens: int = 400) -> str:
        """Thin async LLM call — returns the model's text or raises on failure."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": max_tokens, "temperature": 0.7, "num_ctx": 4096},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload)
            resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()

    @staticmethod
    def _context_has_data(context_text: str) -> bool:
        """True if the context block contains at least one real data item (bullet, tick, alert)."""
        for line in context_text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("• ", "✓ ", "✗ ", "~ ", "[WARNING]", "[CRITICAL]", "[INFO]")):
                return True
            # Named data rows: "1. [TAG] item" pattern from daily_focus
            if stripped and stripped[0].isdigit() and ". [" in stripped:
                return True
        return False

    async def _synthesize_mission(self, context_text: str, kind: str, result: dict) -> "AssistantResponse":
        """Synthesize a briefing from real data. If data is empty, returns rendered text directly."""
        _TITLES = {
            "morning_briefing": "Briefing",
            "daily_focus": "Daily Focus",
            "daily_briefing": "Daily Briefing",
            "weekly_review": "Weekly Review",
            "evening_review": "Evening Review",
        }
        title = _TITLES.get(kind, "Mission Control")

        # Short-circuit: if the rendered text has no data items, the LLM has nothing
        # to synthesize and would only add noise or fabricated filler. Return as-is.
        if not self._context_has_data(context_text):
            return self._simple_response(title, context_text)

        # Data fence — each prompt begins with a hard boundary instruction.
        # The data block is enclosed in delimiters so the model knows exactly what
        # is source material vs. instruction. Every sentence must trace to the block.
        _FENCE_INSTRUCTION = (
            "ABSOLUTE RULE: Your response must contain ONLY information present in the "
            "=== DATA === block below. Every sentence you write must trace directly to a "
            "line in that block. Do not add context, background, causes, implications, or "
            "analysis that do not appear explicitly. Do not speculate. Do not complete "
            "sparse data with plausible details. If a field has no value in the data, "
            "do not mention it. If data is limited, your response must be limited too.\n\n"
        )
        _PROMPTS = {
            "morning_briefing": (
                _FENCE_INSTRUCTION +
                "You are SILVIA giving a morning briefing. Synthesize the data into a "
                "concise operational picture. Mention only what is in the data. "
                "If a section is empty, skip it entirely. One top priority if obvious from the data."
            ),
            "daily_focus": (
                _FENCE_INSTRUCTION +
                "You are SILVIA. Synthesize the priority-ranked items into a clear, actionable "
                "focus recommendation covering the top items. Report only what is in the data."
            ),
            "weekly_review": (
                _FENCE_INSTRUCTION +
                "You are SILVIA giving a weekly review. Report what was done, what is in progress, "
                "and what is coming up — using only the data provided. Do not speculate."
            ),
            "evening_review": (
                _FENCE_INSTRUCTION +
                "You are SILVIA giving an end-of-day review. Report what was completed, "
                "what still needs attention, and any alerts — using only the data provided. "
                "If nothing was completed, say so. Never invent activity."
            ),
            "daily_briefing": (
                _FENCE_INSTRUCTION +
                "You are SILVIA giving a comprehensive engineering daily briefing. Cover the "
                "workspace status, top priority project, blocked projects, pending orders, "
                "and recommended next action — using only the data provided. Be concise."
            ),
        }
        system_prompt = _PROMPTS.get(kind, _PROMPTS["morning_briefing"])
        fenced_context = f"=== DATA ===\n{context_text}\n=== END DATA ==="
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": fenced_context},
        ]
        try:
            answer = await self._call_llm(messages)
        except Exception:
            answer = context_text  # fall back to raw structured text on LLM failure
        return self._simple_response(title, answer)

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

    def _grounded_brain63_response(self, title: str, answer) -> AssistantResponse:
        """Build AssistantResponse with Brain63 source paths in the sources field."""
        from backend.app.models.assistant import SourceReference
        sources = [
            SourceReference(
                title=p.split("/")[-1].replace(".md", "").replace("_", " "),
                url=f"obsidian://{p}",
                source="Brain63",
                category="knowledge",
            )
            for p in (answer.sources or [])
        ]
        confidence = {"high": 0.9, "medium": 0.75, "low": 0.5}.get(
            getattr(answer, "confidence", "medium"), 0.75
        )
        return AssistantResponse(
            mode="conversation",
            title=title,
            answer=answer.text,
            confidence=confidence,
            reasoning="Retrieved from Brain63 (Obsidian vault).",
            processing_time_ms=0,
            sources=sources,
            logs=[CommandLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                title=title,
                detail=answer.text[:200],
            )],
            payload={"speech_text": sanitize_for_speech(answer.text)},
        )

    def _projects_from_brain63_or_registry(self, query: str, category: str = "") -> AssistantResponse:
        """Return a grounded project listing from Brain63 if available, else static registry."""
        from backend.app.services.project_registry import list_projects
        from backend.app.models.assistant import SourceReference
        if self.brain63_service:
            try:
                search_q = f"{category} projects overview" if category else "projects overview status"
                chunks = self.brain63_service.search(search_q, top_k=8)
                if chunks:
                    seen_paths: list = []
                    sources: list = []
                    lines: list = []
                    for c in chunks[:6]:
                        if c.file_path not in seen_paths:
                            seen_paths.append(c.file_path)
                            sources.append(SourceReference(
                                title=c.file_path.split("/")[-1].replace(".md", "").replace("_", " "),
                                url=f"obsidian://{c.file_path}",
                                source="Brain63",
                                category="knowledge",
                            ))
                        from backend.app.services.brain63_service import _first_sentence_or_line
                        first = _first_sentence_or_line(c.content)
                        if first and first not in lines:
                            lines.append(f"**{c.project}** [{c.file_path.split('/')[-1]}]: {first[:180]}")
                    if lines:
                        intro = f"From Brain63 ({category + ' ' if category else ''}projects):"
                        answer = intro + "\n\n" + "\n".join(lines[:6])
                        return AssistantResponse(
                            mode="conversation",
                            title="Brain63",
                            answer=answer,
                            confidence=0.85,
                            reasoning="Retrieved from Brain63 vault.",
                            processing_time_ms=0,
                            sources=sources,
                            logs=[CommandLogEntry(
                                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                title="Brain63",
                                detail=answer[:200],
                            )],
                            payload={"speech_text": sanitize_for_speech(answer)},
                        )
            except Exception as exc:
                logger.debug("Brain63 project search failed: %s", exc)
        # Fallback to static registry
        fallback = (
            f"Known projects: {list_projects()}. "
            "Say the project name for details, or 'show tasks' to see what's queued."
        )
        return self._simple_response("Projects", fallback)

    def _brain63_sources_for_query(self, query: str) -> list:
        """Return SourceReference list for Brain63 entities mentioned in the query."""
        if not self.brain63_service:
            return []
        from backend.app.models.assistant import SourceReference
        raw_mentions = {
            m.group(0).lower().replace(" ", "").replace("-", "")
            for m in _ENTITY_DETECT_RE.finditer(query)
        }
        if not raw_mentions:
            return []
        seen: set = set()
        sources: list = []
        for entity in sorted(raw_mentions):
            try:
                chunks = self.brain63_service.search(
                    query=entity, entity_hint=entity, top_k=4
                )
                for c in chunks:
                    if c.file_path not in seen:
                        seen.add(c.file_path)
                        sources.append(SourceReference(
                            title=c.file_path.split("/")[-1].replace(".md", "").replace("_", " "),
                            url=f"obsidian://{c.file_path}",
                            source="Brain63",
                            category="knowledge",
                        ))
            except Exception:
                pass
        return sources[:6]

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

    async def _generate_grounded_answer(self, query: str, sources, voice: bool = False) -> str:
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
            {"role": "system", "content": build_system_prompt(query, voice=voice)},
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

    def _has_pending(self) -> bool:
        """A set pending confirmation means SILVIA is genuinely awaiting the
        user's reply (yes/no, a choice, etc.) — an intent signal, not punctuation."""
        return any((
            self._pending_deletion, self._pending_ssh, self._pending_command,
            self._pending_email, self._pending_gcal_delete, self._pending_suggestion,
        ))

    def _pending_reason(self) -> str:
        """Map a set pending confirmation to a follow-up reason."""
        if self._pending_command:
            return "approval"
        if self._pending_suggestion:
            return "approval"
        if self._pending_email or self._pending_gcal_delete or self._pending_deletion or self._pending_ssh:
            return "confirmation"
        return "confirmation"

    def _decide_followup(self, text: str, voice: bool) -> tuple[bool, str]:
        """Deterministically decide expects_reply + reason for a response, and (for
        voice turns) record the decision for 'show last voice decision'."""
        has_pending = self._has_pending()
        expects, reason = should_enter_followup(text or "", has_pending, self._pending_reason())
        if voice:
            global _LAST_VOICE_DECISION
            _LAST_VOICE_DECISION = {
                "ts": time.strftime("%H:%M:%S", time.localtime()),
                "response": (text or "").strip()[:300],
                "expects_reply": expects,
                "followup_reason": reason,
                "next_state": "WAITING_FOR_REPLY" if expects else "WAKE_LISTENING",
                "why": _followup_explanation(text or "", expects, reason, has_pending),
            }
            logger.info(
                "[VOICE_DECISION] expects_reply=%s reason=%s next=%s | %r",
                expects, reason, _LAST_VOICE_DECISION["next_state"], (text or "")[:80],
            )
        return expects, reason

    async def _enrich_with_memory(self, query: str) -> str:
        """Return a memory context block to prepend to the system prompt, or ''."""
        if not self.semantic_memory_service:
            return ""
        try:
            results = await self.semantic_memory_service.search(query, top_k=3, min_similarity=0.60)
            if not results:
                return ""
            lines = ["Relevant past conversations (for context only — do not cite directly):"]
            for r in results:
                lines.append(f"- User asked: {r['user_msg'][:120]}")
                lines.append(f"  SILVIA said: {r['assistant_reply'][:120]}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _build_conv_messages(
        self,
        query: str,
        goal: str,
        history: list[dict],
        threads: str = "",
        allow_question: bool | None = None,
        voice: bool = False,
        brain63_ctx: str = "",
        node_ctx: str = "",
    ) -> list[dict]:
        """Build the message list for a conversational turn (goal is set).

        Uses _CONV_BASE + per-goal few-shot examples instead of SILVIA_CORE.
        SILVIA_CORE contains 'command center / mission control' framing that
        causes gemma3:4b to generate sci-fi status dialogue ('I am functioning
        as designed') even when GOAL: SOCIAL is appended. Instructions cannot
        override strong training patterns in a 4B model. Few-shot examples in
        the message history reliably guide completion to the right register.
        """
        from backend.app.services.persona import (
            _CONV_BASE, _CONV_EXAMPLES, GOAL_PROMPTS,
            CURIOSITY_ON, CURIOSITY_OFF, VOICE_ADDENDUM,
        )
        system = _CONV_BASE
        if goal in GOAL_PROMPTS:
            system += "\n\n" + GOAL_PROMPTS[goal]
        # Threads for goals where open-context is useful (not social/engage/support)
        if threads and goal in ("assist", "celebrate", "explore"):
            system += "\n\n" + threads
        # Brain63 context — injected after goal prompt, before curiosity gate.
        # Grounds any entity references the LLM might make.
        if brain63_ctx:
            system += "\n\n" + brain63_ctx
        # Node registry context — live device state from NodeService.
        if node_ctx:
            system += "\n\n" + node_ctx
        if allow_question is True:
            system += "\n\n" + CURIOSITY_ON
        elif allow_question is False:
            system += "\n\n" + CURIOSITY_OFF
        if voice:
            system += "\n\n" + VOICE_ADDENDUM

        messages: list[dict] = [{"role": "system", "content": system}]
        # Few-shot examples anchor the model to SILVIA's conversational register.
        # Injected before history so real history takes recency precedence.
        messages.extend(_CONV_EXAMPLES.get(goal, []))
        # Recent real turns — cap to keep context short for the small model.
        messages.extend(history[-6:] if len(history) > 6 else history)
        messages.append({"role": "user", "content": query})
        return messages

    _CONV_GOALS = frozenset(("social", "engage", "support", "assist", "celebrate", "explore", "banter"))

    async def _generate_response(
        self, query: str, history: list[dict], voice: bool = False, goal: str | None = None
    ) -> str:
        brain63_ctx = self._brain63_context_block(query)
        node_ctx = self._node_context_block(query)
        if goal in self._CONV_GOALS:
            # Conversational path: minimal prompt + few-shots, no operational context.
            # Threads only for goals where open context genuinely helps.
            threads = (
                self.state.render_block()
                if goal in ("assist", "celebrate", "explore")
                else ""
            )
            messages = self._build_conv_messages(
                query, goal, history,
                threads=threads,
                allow_question=self.state.allow_question(goal),
                voice=voice,
                brain63_ctx=brain63_ctx,
                node_ctx=node_ctx,
            )
        else:
            # Operational path: full SILVIA_CORE + memory enrichment.
            memory_ctx = await self._enrich_with_memory(query)
            system_content = build_system_prompt(
                query, voice=voice, goal=goal,
                threads=self.state.render_block(),
                allow_question=self.state.allow_question(goal),
            )
            if memory_ctx:
                system_content = system_content + "\n\n" + memory_ctx
            if brain63_ctx:
                system_content = system_content + "\n\n" + brain63_ctx
            if node_ctx:
                system_content = system_content + "\n\n" + node_ctx
            # Presence context — active project/task/topic for follow-up awareness
            try:
                from backend.app.services.presence_service import get_presence
                _pctx = get_presence().build_context_block()
                if _pctx:
                    system_content = system_content + "\n\n" + _pctx
            except Exception:
                pass
            messages = [{"role": "system", "content": system_content}]
            messages.extend(history)
            messages.append({"role": "user", "content": query})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 400, "temperature": 0.7, "num_ctx": 4096},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(OLLAMA_CHAT_URL, json=payload)
                response.raise_for_status()
            rj = response.json()
            content = rj.get("message", {}).get("content", "").strip()
            done_reason = rj.get("done_reason", "")
            logger.info(
                "LLM response: len=%d done_reason=%s goal=%s query=%r",
                len(content), done_reason, goal, query[:80],
            )
            if content:
                if done_reason == "length" and not content[-1] in ".!?)\"'":
                    content = content.rsplit(" ", 1)[0].rstrip(",:;-") + "."
                return content
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
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
        if self.semantic_memory_service:
            import asyncio
            asyncio.create_task(
                self.semantic_memory_service.embed_and_store(
                    request.session_id, request.query, answer
                )
            )

    async def _generate_response_stream(
        self, query: str, history: list[dict], voice: bool = False, goal: str | None = None
    ):
        _t_ctx0 = time.perf_counter()
        _t = time.perf_counter()
        brain63_ctx = self._brain63_context_block(query)
        _brain63_ms = (time.perf_counter() - _t) * 1000
        _t = time.perf_counter()
        node_ctx = self._node_context_block(query)
        _node_ms = (time.perf_counter() - _t) * 1000
        _mem_ms = 0.0
        if goal in self._CONV_GOALS:
            # Conversational path — same split as _generate_response.
            threads = (
                self.state.render_block()
                if goal in ("assist", "celebrate", "explore")
                else ""
            )
            messages = self._build_conv_messages(
                query, goal, history,
                threads=threads,
                allow_question=self.state.allow_question(goal),
                voice=voice,
                brain63_ctx=brain63_ctx,
                node_ctx=node_ctx,
            )
        else:
            # Operational path.
            _t = time.perf_counter()
            memory_ctx = await self._enrich_with_memory(query)
            _mem_ms = (time.perf_counter() - _t) * 1000
            system_content = build_system_prompt(
                query, voice=voice, goal=goal,
                threads=self.state.render_block(),
                allow_question=self.state.allow_question(goal),
            )
            if memory_ctx:
                system_content = system_content + "\n\n" + memory_ctx
            if brain63_ctx:
                system_content = system_content + "\n\n" + brain63_ctx
            if node_ctx:
                system_content = system_content + "\n\n" + node_ctx
            messages = [{"role": "system", "content": system_content}]
            messages.extend(history)
            messages.append({"role": "user", "content": query})
        _ctx_ms = (time.perf_counter() - _t_ctx0) * 1000
        _prompt_chars = sum(len(m.get("content", "")) for m in messages)
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_predict": 60 if voice else 400, "temperature": 0.7, "num_ctx": 4096},
        }
        chunk_count = 0
        full_text = []
        _t_llm = time.perf_counter()
        _ttft_ms = None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", OLLAMA_CHAT_URL, json=payload) as response:
                    response.raise_for_status()
                    done_reason = ""
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                if _ttft_ms is None:
                                    _ttft_ms = (time.perf_counter() - _t_llm) * 1000
                                chunk_count += 1
                                full_text.append(token)
                                yield token
                            if data.get("done"):
                                done_reason = data.get("done_reason", "")
                                break
                        except json.JSONDecodeError:
                            continue
            text = "".join(full_text)
            _gen_ms = (time.perf_counter() - _t_llm) * 1000
            _tok_s = (chunk_count / (_gen_ms / 1000)) if _gen_ms > 0 else 0.0
            _ttft = _ttft_ms if _ttft_ms is not None else _gen_ms
            _rec = {
                "ts": time.strftime("%H:%M:%S", time.localtime()),
                "model": self.model_name, "goal": goal or "operational", "voice": voice,
                "ctx_ms": round(_ctx_ms), "brain63_ms": round(_brain63_ms),
                "node_ms": round(_node_ms), "mem_ms": round(_mem_ms),
                "ttft_ms": round(_ttft), "gen_ms": round(_gen_ms),
                "tokens": chunk_count, "tok_s": round(_tok_s, 1),
                "prompt_chars": _prompt_chars, "query": query[:60],
            }
            _LLM_TIMINGS.append(_rec)
            logger.info(
                "[LLM_TIMING] ttft_ms=%d ctx_ms=%d (mem=%d brain63=%d node=%d) gen_ms=%d "
                "tokens=%d tok_s=%.1f prompt_chars=%d model=%s goal=%s",
                round(_ttft), round(_ctx_ms), round(_mem_ms), round(_brain63_ms), round(_node_ms),
                round(_gen_ms), chunk_count, _tok_s, _prompt_chars, self.model_name, goal or "operational",
            )
            if done_reason == "length" and text and text[-1] not in ".!?)\"'":
                yield "."
        except Exception as exc:
            logger.error("Streaming response failed: %s", exc)
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
        _voice = bool(request.metadata.get("voice"))

        memory_response = self._handle_memory_command(request)
        if memory_response is not None:
            self._persist_turn(request, memory_response.answer)
            memory_response.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": memory_response.model_dump()})
            return

        # ── Command Router v2: classify before execution ────────────────────
        _raw_q = strip_wake_prefix(request.query.strip())
        _route = classify(_raw_q)
        log_route(_route)

        if _route.owner == "RoutingLog":
            _is_last = bool(re.match(r"^(?:show\s+)?last\s+route", _raw_q, re.I))
            _rl_text = format_last_route() if _is_last else format_routing_log()
            self._persist_turn(request, _rl_text)
            _rl_resp = self._simple_response("Command Routing", _rl_text)
            _rl_resp.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": _rl_resp.model_dump()})
            return

        # ── Presence Mode (Phase 16C) — MUST be in streaming path too ─────
        from backend.app.services.presence_service import get_presence
        _presence = get_presence()
        _presence_resp = await self._handle_presence_command(_raw_q, _presence, request)
        if _presence_resp is not None:
            self._persist_turn(request, _presence_resp.answer)
            _presence_resp.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": _presence_resp.model_dump()})
            return
        _presence._last_interaction = __import__("time").time()
        # ──────────────────────────────────────────────────────────────────

        # ── Context-aware SSH ─────────────────────────────────────────────
        if _route.owner == "SSH":
            _ssh_resp = await self._handle_contextual_ssh(_raw_q, _presence, request)
            if _ssh_resp is not None:
                self._persist_turn(request, _ssh_resp.answer)
                _ssh_resp.processing_time_ms = (time.perf_counter() - started) * 1000
                _ssh_resp.expects_reply, _ssh_resp.followup_reason = self._decide_followup(_ssh_resp.answer, _voice)
                yield json.dumps({"type": "full", "response": _ssh_resp.model_dump()})
                return
        # ──────────────────────────────────────────────────────────────────

        if _CAP_WHAT_CAN_RE.match(_raw_q) or _CAP_LIMITS_RE.match(_raw_q) or _CAP_IMPROVE_RE.search(_raw_q):
            _cap_resp = await self._generate_capability_response(_raw_q, request)
            self._persist_turn(request, _cap_resp.answer)
            _cap_resp.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": _cap_resp.model_dump()})
            return
        if _MY_PROJECTS_RE.search(_raw_q):
            from backend.app.services.project_registry import list_projects
            _proj_ans = (
                f"Known projects: {list_projects()}. "
                "Say the project name for details, or 'show tasks' to see what's queued."
            )
            _proj_resp = self._simple_response("Projects", _proj_ans)
            self._persist_turn(request, _proj_ans)
            _proj_resp.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": _proj_resp.model_dump()})
            return

        # ── Entity registry interceptors ───────────────────────────────────────
        _correction_resp = self._handle_user_correction(_raw_q)
        if _correction_resp is not None:
            self._persist_turn(request, _correction_resp.answer)
            _correction_resp.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": _correction_resp.model_dump()})
            return
        _entity_resp = self._handle_entity_query(_raw_q)
        if _entity_resp is not None:
            self._persist_turn(request, _entity_resp.answer)
            _entity_resp.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": _entity_resp.model_dump()})
            return
        # ──────────────────────────────────────────────────────────────────────

        # ── Mission Control fast path ──────────────────────────────────────────
        from backend.app.tools.planner import _regex_mission as _mc_re
        _mc_route = _mc_re(_raw_q)
        if _mc_route is not None:
            _mc_resp = await self._execute_plan(_mc_route, request)
            if _mc_resp is not None:
                self._persist_turn(request, _mc_resp.answer)
                _mc_resp.processing_time_ms = (time.perf_counter() - started) * 1000
                _mc_resp.expects_reply, _mc_resp.followup_reason = self._decide_followup(_mc_resp.answer, _voice)
                yield json.dumps({"type": "full", "response": _mc_resp.model_dump()})
                return
        # ──────────────────────────────────────────────────────────────────────

        # ── Social Conversation Engine ─────────────────────────────────────────
        _quick_reply, _social_goal = route_social(_raw_q)

        logger.info(
            "[ROUTE] query=%r | social_quick=%s | social_goal=%s",
            _raw_q[:120],
            _quick_reply is not None,
            _social_goal,
        )

        if _quick_reply is not None:
            _sr = self._simple_response("", _quick_reply)
            self._persist_turn(request, _quick_reply)
            _sr.processing_time_ms = (time.perf_counter() - started) * 1000
            yield json.dumps({"type": "full", "response": _sr.model_dump()})
            return

        if _social_goal is not None:
            _history: list[dict] = []
            if self.memory_service:
                _history = self.memory_service.get_ollama_messages(request.session_id, limit=10)
            self.state.note_query(
                _raw_q, _social_goal, is_builder=is_builder_topic(_raw_q)
            )
            _full_text = ""
            async for _token in self._generate_response_stream(
                _raw_q, _history,
                voice=bool(request.metadata.get("voice")),
                goal=_social_goal,
            ):
                _full_text += _token
                yield json.dumps({"type": "token", "token": _token})
            if not _full_text:
                _full_text = "The local model is unavailable — check that Ollama is running."
            self._persist_turn(request, _full_text)
            _elapsed = (time.perf_counter() - started) * 1000
            _expects, _fu_reason = self._decide_followup(_full_text, _voice)
            yield json.dumps({
                "type": "done",
                "speech_text": sanitize_for_speech(_full_text),
                "processing_time_ms": _elapsed,
                "expects_reply": _expects,
                "followup_reason": _fu_reason,
                "agents": [{"name": "Conversation Core", "role": "direct_assistant",
                            "state": "active", "confidence": 72,
                            "summary": f"Social ({_social_goal}) streamed."}],
                "logs": [{"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "title": "Conversation",
                          "detail": f"Social ({_social_goal}) — streamed in {_elapsed:.0f}ms."}],
            })
            return
        # ──────────────────────────────────────────────────────────────────────

        # Operational path.
        command_response = await self._handle_local_command(request)
        if command_response is not None:
            self._persist_turn(request, command_response.answer)
            command_response.processing_time_ms = (time.perf_counter() - started) * 1000
            command_response.expects_reply, command_response.followup_reason = self._decide_followup(command_response.answer, _voice)
            yield json.dumps({"type": "full", "response": command_response.model_dump()})
            return

        use_web = False

        if self.execution_engine is not None:
            from backend.app.orchestration.execution_engine import is_multistep
            if is_multistep(_raw_q):
                exec_response = await self.execution_engine.run(_raw_q, request)
                if exec_response is not None:
                    self._persist_turn(request, exec_response.answer)
                    exec_response.processing_time_ms = (time.perf_counter() - started) * 1000
                    exec_response.expects_reply, exec_response.followup_reason = self._decide_followup(exec_response.answer, _voice)
                    yield json.dumps({"type": "full", "response": exec_response.model_dump()})
                    return

        use_web = _route.category == "web_search" or request.metadata.get("use_web") is True
        tool_decision = await plan(_raw_q, allow_web=use_web)

        logger.info(
            "[ROUTE] category=%s use_web=%s | plan_action=%s | plan_tool=%s",
            _route.category, use_web,
            tool_decision.get("action"),
            tool_decision.get("name") or [c.get("name") for c in tool_decision.get("calls", [])],
        )

        if tool_decision.get("action") in ("call_tool", "call_tools"):
            tool_response = await self._execute_plan(tool_decision, request)
            if tool_response is not None:
                self._persist_turn(request, tool_response.answer)
                tool_response.processing_time_ms = (time.perf_counter() - started) * 1000
                tool_response.expects_reply, tool_response.followup_reason = self._decide_followup(tool_response.answer, _voice)
                yield json.dumps({"type": "full", "response": tool_response.model_dump()})
                return
            logger.warning("[ROUTE] plan selected tool but _execute_plan returned None — falling through to LLM")

        # Web path — grounded generation doesn't stream well, return full result
        if use_web and self.web_service is not None:
            from backend.app.web.schemas.models import SearchRequest as _SR
            search_response = await self.web_service.search(
                _SR(
                    query=_raw_q,
                    category=request.metadata.get("web_category", self._infer_search_category(_raw_q)),
                    limit=4,
                )
            )
            sources = self.web_service.to_sources(search_response)
            answer = await self._generate_grounded_answer(
                _raw_q, sources, voice=bool(request.metadata.get("voice"))
            )
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
                agents=[AgentStatus(name="Web Tool", role="search", state="complete", confidence=85, summary=f"Searched: {_raw_q}")],
                logs=[CommandLogEntry(timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), title="Web search", detail=f"Query: {_raw_q}")],
                payload={"speech_text": sanitize_for_speech(answer)},
            )
            yield json.dumps({"type": "full", "response": web_resp.model_dump()})
            return

        # LLM streaming path
        history: list[dict] = []
        if self.memory_service:
            history = self.memory_service.get_ollama_messages(request.session_id, limit=10)

        self.state.note_query(_raw_q, None, is_builder=is_builder_topic(_raw_q))
        full_text = ""
        async for token in self._generate_response_stream(
            _raw_q, history, voice=bool(request.metadata.get("voice")),
            goal=None,
        ):
            full_text += token
            yield json.dumps({"type": "token", "token": token})

        if not full_text:
            full_text = "The local model is unavailable — check that Ollama is running."

        self._persist_turn(request, full_text)
        elapsed = (time.perf_counter() - started) * 1000
        expects, fu_reason = self._decide_followup(full_text, _voice)
        yield json.dumps({
            "type": "done",
            "speech_text": sanitize_for_speech(full_text),
            "processing_time_ms": elapsed,
            "expects_reply": expects,
            "followup_reason": fu_reason,
            "agents": [{"name": "Conversation Core", "role": "direct_assistant", "state": "active", "confidence": 72, "summary": "Handled through the streaming conversation path."}],
            "logs": [{"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "title": "Conversation", "detail": f"Streamed with {len(history) // 2} prior turns in {elapsed:.0f}ms."}],
        })

    def _render_time_here(self, data: dict) -> str:
        if data.get("place"):
            return f"It's currently {data['human']} in {data['place']}."
        return f"It's currently {data['human']} ({data['tz']})."

    def _render_time_there(self, data: dict) -> str:
        return f"It's currently {data['human']} in {data['place']} ({data['tz']})."

    def _render_stock(self, data: dict) -> str:
        direction = "▲" if data["change"] >= 0 else "▼"
        sign = "+" if data["change"] >= 0 else ""
        state = data.get("marketState", "")
        state_note = f" ({state})" if state and state != "REGULAR" else ""
        return (
            f"{data['name']} ({data['symbol']}) is trading at "
            f"{data['currency']} {data['price']:.2f}{state_note} — "
            f"{direction} {sign}{data['change']:.2f} ({sign}{data['changePercent']:.2f}%) today. "
            f"(Source: Yahoo Finance — prices are delayed ~15 min.)"
        )

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
        return " ".join(parts).rstrip(".") + ". (Source: OpenWeather)"

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
