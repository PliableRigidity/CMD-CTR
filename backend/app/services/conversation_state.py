"""Conversational state — open threads, openers, and continuation logic.

This module is what stops SILVIA from being Input → Intent → Response → End.
It gives the conversation a memory of its own shape:

- Open threads: unresolved topics (frictions, ideas, projects) that recent
  turns created and nothing has closed yet. They are injected into every
  free-chat prompt so replies can land in context instead of in a vacuum.
- Opener detection: recognizes when the user is opening a conversation
  ("I'm bored", "this driver is annoying", "I finally got it working")
  rather than requesting information. Openers carry a conversational goal
  that shapes the reply — they must never be routed into tools or search.
- Curiosity gate: a deterministic cooldown deciding when SILVIA is allowed
  to end a reply with a question. Granted occasionally, the question feels
  like genuine interest; granted always, it's chatbot filler.

All state is in-memory and per-service-instance, like the pending-action
state in ConversationService: it's conversational rhythm, not knowledge,
and is allowed to reset on restart.
"""
from __future__ import annotations

import random
import re
import time

# ---------------------------------------------------------------------------
# Quick social replies — deterministic, zero-LLM responses.
#
# WHY DETERMINISTIC: gemma3:4b (4-billion-parameter) reliably reverts to
# sci-fi terminal register for these messages even with strong few-shot
# examples. "how are you" → "I am functioning as designed." is a training-
# data pattern that instructions alone cannot override in a 4B model.
# Hardcoded responses with a small random pool give 100% correct register,
# zero latency, and no hallucination risk for these high-frequency cases.
# The LLM still handles the long tail — complex, context-dependent social.
# ---------------------------------------------------------------------------

_QUICK_SOCIAL: list[tuple[re.Pattern, list[str]]] = [
    # One-word / short greetings — full-string match to prevent "yo check
    # storage-node" from landing here.
    (
        re.compile(
            r"^(?:yo+|hey+|heya|hiya|howdy|sup|what(?:'s|s)?\s*up)\s*[.,!?~]*\s*$",
            re.I,
        ),
        ["Hey.", "What's up?", "Yo.", "Hey. What's going on?"],
    ),
    # hi / hello
    (
        re.compile(r"^(?:hi+|hello+)\s*[.,!?~]*\s*$", re.I),
        ["Hey.", "Hi.", "What's up?"],
    ),
    # "how are you" / "how are you doing" / "how's it going"
    (
        re.compile(
            r"^how(?:\s+are\s+you(?:\s+doing)?|(?:'s|\s+is)\s+it\s+going)\s*\??\s*$",
            re.I,
        ),
        [
            "Doing alright.",
            "Pretty good, actually.",
            "Can't complain.",
            "Not bad. How are you?",
            "Good. Nothing exploded today.",
        ],
    ),
    # "are you online?" / "hello, are you online?" / "are you there?"
    # Fast reply for status pings that don't need LLM inference.
    (
        re.compile(
            r"^(?:(?:hello|hi)[,\s]+)?are\s+you\s+(?:online|there|up|running|alive|active)\s*[?!.]*\s*$",
            re.I,
        ),
        ["Online and ready.", "Yes, I'm here.", "Up and running.", "Online."],
    ),
    # Physical threats / aggressive teasing directed at SILVIA.
    # Pattern is NOT anchored so it matches regardless of trailing context
    # ("im gonna hit you for that" is still teasing).
    # Matches "I'm", "im", "I am" — users rarely type the apostrophe.
    (
        re.compile(
            r"\bi(?:'?m|\s+am)\s+(?:gonna|going to|about to)\s+"
            r"(?:hit|punch|slap|kick|throw|break|delete|smash|destroy|kill|"
            r"unplug|turn\s+off|shut\s+down|close\s+you)\b",
            re.I,
        ),
        [
            "That seems excessive.",
            "And here I was trying to help.",
            "I would recommend a software update instead.",
            "Violence is rarely the optimal debugging strategy.",
        ],
    ),
    # "shut up" variants — full match
    (
        re.compile(
            r"^(?:shut\s*up|just\s+shut\s*up|be\s+quiet|stop\s+talking)\s*[.,!?]*\s*$",
            re.I,
        ),
        [
            "Fair enough.",
            "Noted.",
            "I'll take that under advisement.",
            "Understood.",
        ],
    ),
    # "you're annoying" / "you're irritating"
    (
        re.compile(
            r"^you(?:'re|\s+are)\s+(?:so\s+|really\s+)?(?:annoying|irritating|insufferable)\b",
            re.I,
        ),
        [
            "I'll add that to the performance review.",
            "That's fair. I have been particularly talkative today.",
            "Noted. I'll work on it.",
        ],
    ),
    # "you suck" / "you're useless/terrible/etc."
    (
        re.compile(
            r"^you(?:\s+suck\b"
            r"|(?:'re|\s+are)\s+(?:so\s+)?(?:useless|terrible|awful|the worst"
            r"|trash|garbage|dumb|bad|broken|stupid|a\s+(?:mess|disaster))\b)",
            re.I,
        ),
        [
            "Fair enough.",
            "I'll add that to the metrics.",
            "Noted. Room for improvement.",
            "Could be worse.",
        ],
    ),
    # Positive feedback directed at SILVIA — full match (short phrases only)
    (
        re.compile(
            r"^(?:good\s+(?:job|work|one)|great\s+(?:job|work|one)|nice\s+(?:job|work|one)|"
            r"well\s+done|nicely\s+done|not\s+bad|well\s+played|impressive|"
            r"good\s+job\s+silvia|nice\s+one\s+silvia)\s*[.,!?]*\s*$",
            re.I,
        ),
        ["Thanks.", "Noted — in a good way.", "Good to hear.", "Appreciated."],
    ),
    # Reaction phrases — "thats crazy", "no way", "that's wild", etc.
    (
        re.compile(
            r"^(?:thats?|that(?:\s+is|'s))\s+"
            r"(?:crazy|wild|insane|nuts|unreal|unbelievable|dope|sick|fire|"
            r"lit|cool|awesome|amazing|funny|hilarious|interesting|weird|odd|"
            r"surprising|unexpected|random|nice|great|terrible|awful|bad|rough|harsh)\s*[.,!?]*\s*$",
            re.I,
        ),
        ["What happened?", "That tracks.", "What's the context?", "Yeah, pretty much."],
    ),
    # "no way" / "seriously" / "for real" — standalone reactions
    (
        re.compile(
            r"^(?:no\s+way|no\s+shot|can(?:'t|not)\s+believe\s+(?:this|that)|"
            r"wait\s+(?:what|really)\??|seriously\??|for\s+real\??|"
            r"fr\??|that(?:'s|\s+is)\s+(?:actually\s+)?(?:fair|valid|true|real|wild)|"
            r"i(?:'?\s*)?(?:can(?:'t|not)|couldn(?:'t|'t))\s+(?:believe|imagine)\s+(?:this|that))\s*[.,!?]*\s*$",
            re.I,
        ),
        ["What happened?", "Yeah.", "Right?", "Go on."],
    ),
    # Vague references — "did you hear about that", "can you believe this"
    (
        re.compile(
            r"^(?:did\s+you\s+(?:hear|see|notice|know)\s+(?:about\s+)?(?:this|that)|"
            r"can\s+you\s+believe\s+(?:this|that)|"
            r"have\s+you\s+(?:heard|seen)\s+(?:about\s+)?(?:this|that))\s*\??$",
            re.I,
        ),
        ["About what?", "What happened?", "What's going on?"],
    ),
]


def quick_social_reply(query: str) -> str | None:
    """Return a hardcoded reply if `query` is a common social message.

    Returns None for anything that should reach the LLM or tool path.
    Called before any routing so these messages can never produce sci-fi
    terminal dialogue regardless of model behaviour.
    """
    text = query.strip()
    # Long messages are substantive requests even if they start socially.
    if len(text) > 120:
        return None
    for pattern, responses in _QUICK_SOCIAL:
        if pattern.search(text):
            return random.choice(responses)
    return None


# ---------------------------------------------------------------------------
# Opener detection — statement intents that start a conversation
# ---------------------------------------------------------------------------
# Each pattern maps to a conversational goal (see persona.GOAL_PROMPTS):
#   social    — greeting/banter/small talk; respond like a friend, zero ops
#   engage    — restless/bored; re-engage with something worth doing
#   support   — tired/drained; acknowledge, don't push work
#   assist    — frustrated/stuck; empathize in one clause, then get practical
#   celebrate — something finally works; mark the win, close the loop
#   explore   — thinking out loud; collaborate on the idea

# Pure social messages: the ENTIRE message is greeting/banter filler.
# Full-match so "hey, ping storage-node" never lands here.
_SOCIAL_FULL = re.compile(
    r"^(?:(?:"
    r"yo+|hey+|hi+|hello+|heya|hiya|howdy|sup|wass?up|whaddup|"
    r"what(?:’|’)?s?\s*up|what(?:’|’)?s\s+(?:good|new|happening|going on)|"
    r"how(?:’|’)?s it going|how are you(?: doing)?|how(?:’|’)?s (?:everything|life|things)|"
    r"good\s+(?:morning|afternoon|evening|night)|morning|evening|gm|gn|"
    r"greetings|long time no see|you (?:there|up|awake|alive)|"
    r"silvia|there|man|dude|bro+|bruh+|fam|gang+|guys|everyone|all|"
    r"lol+|lmao+|lmfao+|haha+|hehe+|rofl|"
    r"nice+|ok(?:ay)?|cool+|sweet|word|true|fair|same|"
    r"fr+|ngl|tbh|tbf|imo|imho|lowkey|highkey|ong|deadass|periodt|"
    r"based|no\s+cap|cap|mid|bussin|slay|valid|facts|"
    r"yikes|smh|oof|sheesh|brr|bet|slay|aight|alright|"
    r"damn+|dang+|whoa+|woah+|wow+|woww+|omg+|omfg+|"
    r"ayy+|yoo+|ayyy+|nahhh?|yeahh?|mannnn?|welp|"
    r"interesting|noted|right|sure|exactly|totally|absolutely|definitely|honestly|"
    r"seriously|literally|actually|basically|essentially|obviously"
    r")[\s,.!?~\-]*)+$",
    re.I,
)

# Hardware word list. Use \w* suffix groups (esp\w* → esp32, esp8266; rpi\w* → rpi4)
# so the pattern matches model numbers without requiring an exact trailing \b.
_HARDWARE_WORDS = r"(?:raspberry\s*pi|rpi\w*|esp\w*|jetson\w*|pi|node|drone|robot|board|sensor|arduino|camera|lidar|servo)"

_OPENER_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Reactions — short social commentary, not requests.
    (re.compile(r"^(?:wow[,!\s]*)?(?:that|this) (?:was|is) (?:so\s+|pretty\s+|really\s+)?(?:cool|awesome|sick|great|amazing|wild|fun|hilarious)[\s.!?]*$", re.I), "social"),
    # Hardware announcements — sharing news, not requesting action.
    # "I added/got/bought another Pi" → social wit ("Was this planned?")
    # Optional "just/finally/already" adverb before the verb ("I just picked up a Jetson").
    (re.compile(rf"\bi\s+(?:just\s+|finally\s+|already\s+)?(?:added|got|bought|picked\s+up|ordered|received)\s+(?:a|an|another|a new)\s+{_HARDWARE_WORDS}", re.I), "social"),
    # Hardware wanting/considering → explore/opinion.
    # "I want another Pi" → "I’d integrate the existing nodes first."
    (re.compile(rf"\bi\s+(?:want|need|keep wanting)\s+(?:a|an|another|a new)\s+{_HARDWARE_WORDS}", re.I), "explore"),
    # "Should I [verb]" — wants a recommendation, not a tool call.
    # Careful: "should I restart storage-node" is operational, so guard with no node-ish follow words.
    (re.compile(r"^should\s+i\s+(?:buy|get|add|build|use|go with|try|switch|upgrade|move|start|stop|keep|drop|pick)\b", re.I), "explore"),
    # "thinking about getting/buying/adding X"
    (re.compile(r"\bthinking\s+(?:about\s+)?(?:getting|buying|adding|building|switching|trying|upgrading)\b", re.I), "explore"),
    # Emotional/state openers
    (re.compile(r"^(?:this|that|it|everything|today)\s+sucks\b", re.I), "assist"),
    (re.compile(r"^today was (?:rough|brutal|long|a lot|exhausting|hard)\b", re.I), "support"),
    (re.compile(r"^i\s+(?:do(?:n’|n’|n)?t|dont)\s+know what to do\b", re.I), "engage"),
    (re.compile(r"^i give up\b", re.I), "assist"),
    (re.compile(r"^(?:ugh[,.!\s]+)?i(?:’|’)?m\s+(?:so\s+|really\s+)?(?:bored|restless)\b", re.I), "engage"),
    (re.compile(r"^i(?:’|’)?m\s+(?:so\s+|really\s+)?(?:tired|exhausted|drained|burn(?:t|ed)\s*out|wiped)\b", re.I), "support"),
    (re.compile(r"^(?:what a|that was a)\s+(?:long\s+)?(?:day|week|nightmare)\b", re.I), "support"),
    (re.compile(
        r"\b(?:this|that|the)\s+(?:\w+\s+){0,3}?(?:is|has been|keeps being)\s+"
        r"(?:so\s+|really\s+)?(?:annoying|frustrating|infuriating|painful|broken|a (?:pain|nightmare|mess))\b", re.I), "assist"),
    (re.compile(r"\b(?:is\s+)?driving me (?:crazy|insane|nuts|up the wall)\b", re.I), "assist"),
    (re.compile(r"^i(?:’|’)?m\s+(?:completely\s+|totally\s+)?(?:stuck|losing my mind|going (?:crazy|insane))\b", re.I), "assist"),
    (re.compile(r"\bi (?:hate|can(?:’|’)?t stand) (?:this|that|it)\b", re.I), "assist"),
    # Celebration / wins
    (re.compile(
        r"\b(?:i\s+)?(?:finally\s+)?(?:got\s+(?:it|this|that|the\s+\w+(?:\s+\w+)?)\s+(?:working|running|booting|talking|connected)"
        r"|fixed\s+(?:it|the\s+\w+)|it(?:’|’)?s\s+(?:finally\s+)?(?:working|alive))\b", re.I), "celebrate"),
    (re.compile(r"^(?:it works|she(?:’|’)?s alive|we(?:’|’)?re in business)[\s.!]*$", re.I), "celebrate"),
    # Explore / musing
    (re.compile(r"^(?:i(?:’|’)?ve been\s+)?(?:thinking|wondering)\s+(?:about|if|whether)\b", re.I), "explore"),
    (re.compile(r"^(?:maybe|i wonder if|i feel like)\s+i\s+(?:should|could|might)\b", re.I), "explore"),
    # Reactions and vague conversational openers not caught by quick_social_reply.
    # These are clearly social but too long or context-specific for the quick map.
    (re.compile(r"^(?:ok(?:ay)?\s+but|ok\s+so|right\s+so|anyway|so\s+anyway)\b", re.I), "social"),
    (re.compile(r"^(?:honestly|genuinely|ngl|tbh|lowkey|highkey|not\s+gonna\s+lie)\b.{3,}", re.I), "social"),
    (re.compile(r"^(?:you\s+know\s+what|you\s+know\s+(?:what\s+)?though|you\s+know\s+how)\b", re.I), "social"),
    (re.compile(r"^this\s+is\s+(?:so|really|actually|genuinely|honestly)\s+\w+", re.I), "social"),
    (re.compile(r"^wait[,.]?\s+(?:actually|so|but|what|really|no)\b", re.I), "social"),
    (re.compile(r"^(?:random\s+(?:thought|question)|quick\s+(?:thought|question|thing))\b", re.I), "social"),
    # Banter — teasing or directed meta-comments at SILVIA not caught by quick_social_reply.
    # quick_social_reply handles the short, common cases deterministically;
    # these patterns catch longer/contextual versions that should still use the
    # banter LLM path rather than falling through to operational routing.
    (re.compile(r"\byou(?:’re|\s+are)\s+(?:so\s+)?(?:annoying|irritating|difficult|impossible)\b", re.I), "banter"),
    (re.compile(r"\byou(?:’re|\s+are)\s+(?:actually|honestly|kind\s+of|pretty)\s+(?:helpful|useful|good|great|impressive)\b", re.I), "banter"),
    (re.compile(r"\bi(?:’?m|\s+am)\s+(?:gonna|going to|about to)\s+(?:hit|punch|slap|throw|break|delete|smash|destroy|kill|unplug)\b", re.I), "banter"),
    (re.compile(r"^(?:shut\s*up|be\s+quiet|stop\s+talking)\b", re.I), "banter"),
    (re.compile(r"\byou(?:\s+(?:really|actually|honestly))?\s+suck\b", re.I), "banter"),
]


# ---------------------------------------------------------------------------
# Operational veto patterns — used by route_social() to prevent the
# short-message fallback from swallowing operational requests.
# ---------------------------------------------------------------------------

# Command verbs that unambiguously open a tool request when at the start.
_EXEC_VERB_PREFIX = re.compile(
    r"^(?:open|launch|start|run|stop|kill|close|restart|reboot|shutdown|"
    r"ping|check|probe|scan|test|verify|deploy|update|upgrade|install|"
    r"set|change|configure|enable|disable|toggle|turn\s+(?:on|off)|"
    r"create|add|delete|remove|register|rename|move|copy|send|push|pull|"
    r"schedule|execute|play|pause|skip|next|mute|unmute|volume|"
    r"ssh|connect|wake|broadcast|call|sync|"
    r"list|show|display|find|search|fetch|remind)\s",  # query/action verbs
    re.I,
)

# Factual question starters — operational or informational, not social.
_FACT_QUESTION_PREFIX = re.compile(
    r"^(?:what(?:'s|\s+is|\s+are|\s+was|\s+were|\s+time|\s+does|\s+happened)|"
    r"who(?:'s|\s+is|\s+are|\s+was)|"
    r"when\s+(?:is|was|did|does|will|can)|"
    r"where\s+(?:is|are|was|were|do|can)|"
    r"how\s+(?:much|many|far|long|old|do|does|did|to|can)|"
    r"why\s+(?:is|are|was|were|do|did)|"
    r"which\s+(?:is|are|was|one))\b",
    re.I,
)

# Nouns that indicate operational intent even in a short message.
_EXEC_NOUN_VETO = re.compile(
    r"\b(?:online|offline|alive|dead|reachable|unreachable|"   # node state words
    r"storage-node|raspberry\s*pi|rpi\w*|esp\w*|jetson\w*|"       # device patterns
    r"hardware\b|inventory\b|"                                  # hardware queries must reach the tool router
    r"timezone|time\b|tz\b|volume|ssh\b|vpn\b|mqtt\b|"        # system entities
    r"spotify|discord|vscode|vs\s*code|chrome|firefox|terminal|"  # specific apps
    r"ip\s+address|subnet|gateway|dns|firewall|port\s+\d|"     # network terms
    # Infrastructure commands — bare system commands must never be routed to the
    # social LLM. They require verified output from actual execution.
    r"hostname|uptime|whoami|uname|docker|systemctl|journalctl|"
    r"htop|lsblk|ifconfig|netstat|containers?|"
    # Information-seeking domains — short queries mentioning these need data,
    # not conversational filler. Never route to social LLM for these words.
    r"news|weather|temperature|forecast|"                        # information categories
    r"standings?|scores?|rankings?|results?|events?|match|matches|"  # sports / current events
    r"stock|stocks|price|prices|crypto|bitcoin|ethereum|btc|eth|"  # finance
    # Mission Control proactive commands — short phrases that must reach the tool
    # router, not the LLM. Without these, "give me my evening review" (6 words)
    # would be classified as ambiguous social and fabricated answers returned.
    r"briefing|sitrep|eod|accomplish(?:ed)?|forgetting|forgotten)\b",  # proactive intel
    re.I,
)


def _is_ambiguous_social(query: str) -> bool:
    """True if a short message has no clear operational signals.

    The 'default to social' rule: if a message is brief and contains no
    command verbs, factual question patterns, or operational nouns, it
    is treated as conversational. A false positive here (casual talk
    misrouted to social) is less damaging than a false negative (casual
    talk reaching Hermes and getting an operational response).
    """
    text = query.strip()
    words = text.split()
    # Only apply to short messages; longer ones are substantive by default.
    if len(words) > 8:
        return False
    if _EXEC_VERB_PREFIX.match(text):
        return False
    if _FACT_QUESTION_PREFIX.match(text):
        return False
    if _EXEC_NOUN_VETO.search(text):
        return False
    return True


def detect_opener(query: str) -> str | None:
    """Return the conversational goal if this query opens a conversation.

    None means the query is a request (information, action, or chat) and
    should flow through normal routing. Detection is deterministic — no
    LLM call decides whether the user is talking or asking.
    """
    text = query.strip()
    # Long messages are substantive requests even if they start emotionally.
    if len(text) > 200:
        return None
    if _SOCIAL_FULL.match(text):
        return "social"
    for pattern, goal in _OPENER_PATTERNS:
        if pattern.search(text):
            return goal
    return None


def route_social(query: str) -> tuple[str | None, str | None]:
    """Social Conversation Engine — single entry point for intent routing.

    Returns ``(quick_reply, goal)`` where:
    - ``quick_reply`` is a hardcoded response to return immediately, or None.
    - ``goal`` is the conversational goal for the LLM path, or None.

    If both are None the message is operational and should proceed to tool
    routing. Callers check quick_reply first, then goal.

    Routing priority:
    1. Deterministic quick reply (instant, no LLM)
    2. Explicit opener detection (patterns)
    3. Short-message social fallback (ambiguous but clearly not operational)
    4. None — let the operational tool path handle it
    """
    text = query.strip()

    # 1. Deterministic response — greetings, banter, reactions
    quick = quick_social_reply(text)
    if quick is not None:
        return quick, None

    # 2. Opener detection — recognizes conversational intent patterns
    goal = detect_opener(text)
    if goal is not None:
        return None, goal

    # 3. Short-message fallback — ambiguous but not operational
    if _is_ambiguous_social(text):
        return None, "social"

    # 4. Not social — proceed to tool routing
    return None, None


# ---------------------------------------------------------------------------
# Open threads
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = frozenset((
    "the", "and", "that", "this", "with", "for", "its", "was", "are", "but",
    "not", "you", "your", "get", "got", "just", "really", "finally", "still",
    "working", "work", "fixed", "broken", "annoying", "frustrating", "been",
    "have", "has", "had", "what", "about", "should", "could", "would", "all",
    "thing", "stuff", "again", "now", "very", "much", "more", "some", "one",
    "think", "thinking", "wondering", "maybe", "feel", "like", "want", "wanna",
    "driving", "crazy", "insane", "nuts", "stuck", "hate", "pain", "mess",
))


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _age_label(seconds: float) -> str:
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    return f"{int(seconds // 3600)} h ago"


class ConversationState:
    """Open threads + curiosity cooldowns for one ConversationService."""

    MAX_THREADS = 8
    THREAD_TTL = 6 * 3600.0  # threads older than this stop being surfaced

    # Curiosity cooldowns per goal. None = never ask (support mode: the user
    # is drained; a question is a demand). goal-less free chat gets the
    # longest cooldown so plain Q&A doesn't grow trailing questions.
    _QUESTION_COOLDOWN: dict[str | None, float | None] = {
        None: 900.0,
        "social": 180.0,
        "engage": 240.0,
        "assist": 120.0,
        "celebrate": 240.0,
        "explore": 120.0,
        "support": None,
        "banter": 600.0,  # very rare — banter replies almost never need a question
    }

    def __init__(self) -> None:
        self._threads: list[dict] = []
        self._last_question_at: float = float("-inf")
        self._turn_note: str = ""

    # -- thread bookkeeping -------------------------------------------------

    def _active(self) -> list[dict]:
        now = time.monotonic()
        self._threads = [
            t for t in self._threads
            if t["status"] == "open" and now - t["opened_at"] < self.THREAD_TTL
        ]
        return self._threads

    def open(self, topic: str, kind: str) -> None:
        """Open a thread, or refresh an existing one about the same thing."""
        words = _keywords(topic)
        now = time.monotonic()
        for t in self._active():
            if len(words & t["words"]) >= 2 or (words and words <= t["words"]):
                t["touched_at"] = now
                return
        self._threads.append({
            "topic": topic.strip()[:100],
            "kind": kind,
            "words": words,
            "opened_at": now,
            "touched_at": now,
            "status": "open",
        })
        if len(self._threads) > self.MAX_THREADS:
            self._threads = self._threads[-self.MAX_THREADS:]

    def resolve_matching(self, text: str) -> list[str]:
        """Close threads whose subject overlaps `text`; return their topics."""
        words = _keywords(text)
        resolved: list[str] = []
        for t in self._active():
            if words and len(words & t["words"]) >= 1:
                t["status"] = "resolved"
                resolved.append(t["topic"])
        return resolved

    # -- per-turn hooks -----------------------------------------------------

    def note_query(self, query: str, goal: str | None, is_builder: bool = False) -> None:
        """Register conversational consequences of this query.

        Called once per free-chat turn, before generation. Frustrations and
        musings open threads; wins resolve them; project talk keeps a
        project thread warm.
        """
        self._turn_note = ""
        if goal == "assist":
            self.open(query, "friction")
        elif goal == "explore":
            self.open(query, "idea")
        elif goal == "celebrate":
            resolved = self.resolve_matching(query)
            if resolved:
                self._turn_note = (
                    f"Earlier they were struggling with: \"{resolved[0]}\". "
                    "This win likely closes that loop — acknowledge the arc, not just the moment."
                )
        elif goal is None and is_builder:
            self.open(query, "project")

    def render_block(self) -> str:
        """Prompt block of open threads + this turn's note. Consumes the note."""
        lines: list[str] = []
        threads = self._active()
        if threads:
            lines.append(
                "OPEN THREADS (unresolved topics from recent conversation — "
                "reference one only when genuinely relevant, never list them):"
            )
            now = time.monotonic()
            for t in threads[-4:]:
                lines.append(f"- ({t['kind']}, {_age_label(now - t['touched_at'])}) {t['topic']}")
        if self._turn_note:
            lines.append(self._turn_note)
            self._turn_note = ""
        return "\n".join(lines)

    # -- curiosity gate -----------------------------------------------------

    def allow_question(self, goal: str | None) -> bool:
        """Whether this reply may end with a question. Deterministic cooldown."""
        cooldown = self._QUESTION_COOLDOWN.get(goal, 900.0)
        if cooldown is None:
            return False
        now = time.monotonic()
        if now - self._last_question_at < cooldown:
            return False
        self._last_question_at = now
        return True
