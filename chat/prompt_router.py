"""
prompt_router.py – chat/prompt_router.py

Classifies incoming messages into one of several intent types at runtime,
then returns a tailored system-prompt template and metadata about which
sources should be injected.

Intent taxonomy
---------------
FACTUAL_LOOKUP      → "What does a GPU do?" / "What is RAM?"
REPAIR_GUIDANCE     → "How do I fix my screen?" / "My laptop won't charge"
ORDER_STATUS        → "What's the status of my repair?" / "When will it be done?"
TROUBLESHOOT        → "My PC keeps crashing" / "Fan is loud and hot"
GENERAL_SUPPORT     → Everything else (billing, hours, pricing, etc.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from openai import OpenAI
from admin_panel.models import APIKeyConfig

# ---------------------------------------------------------------------------
# Intent constants
# ---------------------------------------------------------------------------

INTENT_FACTUAL_LOOKUP = "factual_lookup"
INTENT_REPAIR_GUIDANCE = "repair_guidance"
INTENT_ORDER_STATUS = "order_status"
INTENT_TROUBLESHOOT = "troubleshoot"
INTENT_GENERAL_SUPPORT = "general_support"

ALL_INTENTS = [
    INTENT_FACTUAL_LOOKUP,
    INTENT_REPAIR_GUIDANCE,
    INTENT_ORDER_STATUS,
    INTENT_TROUBLESHOOT,
    INTENT_GENERAL_SUPPORT,
]


# ---------------------------------------------------------------------------
# Routing result
# ---------------------------------------------------------------------------


@dataclass
class RoutingResult:
    intent: str
    system_prompt: str
    use_faq: bool = True
    use_ifixit: bool = False
    use_order_context: bool = False
    confidence: str = "high"  # "high" | "medium" | "low"
    sources_label: str = ""  # Human-readable label (optional UI)


# ---------------------------------------------------------------------------
# Keyword signal tables (cheap, zero-latency classification)
# ---------------------------------------------------------------------------

_ORDER_STATUS_SIGNALS = [
    r"\border\b",
    r"\bticket\b",
    r"\bmy repair\b",
    r"\bstatus\b",
    r"\bprogress\b",
    r"\bwhen will\b",
    r"\bready\b",
    r"\bpick.?up\b",
    r"\btrack\b",
    r"\bupdate on\b",
    r"\bhow long\b",
]

_TROUBLESHOOT_SIGNALS = [
    r"\bbattery\b",
    r"\bdraining\b",
    r"\bdrain\b",
    r"\bcharging\b",
    r"\bwon.?t charge\b",
    r"\bdead\b",
    r"\bpower\b",
    r"\boverheating\b",
    r"\boverheats\b",
    r"\boverheated\b",
    r"\bhot\b",
    r"\bfan\b",
    r"\bthermal\b",
    r"\bscreen\b",
    r"\bdisplay\b",
    r"\bblack screen\b",
    r"\bno display\b",
    r"\bflicker\b",
    r"\bcracked\b",
    r"\bslow\b",
    r"\blag\b",
    r"\bfreezing\b",
    r"\bfreeze\b",
    r"\bcrash\b",
    r"\bcrashing\b",
    r"\bstutter\b",
    r"\bblue.?screen\b",
    r"\bbsod\b",
    r"\bwon.?t boot\b",
    r"\bwon.?t turn on\b",
    r"\bnot turning on\b",
    r"\bkeeps turning off\b",
    r"\bshuts off\b",
    r"\brestarting\b",
    r"\bkeyboard\b",
    r"\btrackpad\b",
    r"\bspeaker\b",
    r"\bcamera\b",
    r"\bport\b",
    r"\bhinges\b",
    r"\bwater damage\b",
    r"\bissue\b",
    r"\bproblem\b",
    r"\bbroken\b",
    r"\bnot working\b",
    r"\bsomething wrong\b",
    r"\bbehaving\b",
    r"\bacting up\b",
    r"\bweird\b",
    r"\bstrange\b",
    r"\bkeeps\b",
]

_REPAIR_GUIDANCE_SIGNALS = [
    r"\bhow (do i|to)\b",
    r"\bsteps\b",
    r"\bguide\b",
    r"\btutorial\b",
    r"\bfix\b",
    r"\brepair\b",
    r"\bchange\b",
    r"\breplace\b",
    r"\breplacement\b",
    r"\binstall\b",
    r"\bremove\b",
    r"\bdisassemble\b",
    r"\bopen\b.*\blaptop\b",
    r"\bopen\b.*\bphone\b",
    r"\bcan i\b.*\bfix\b",
    r"\bcan i\b.*\breplace\b",
    r"\bdiy\b",
    r"\bmyself\b",
]

_FACTUAL_LOOKUP_SIGNALS = [
    r"\bwhat is\b",
    r"\bwhat are\b",
    r"\bwhat does\b",
    r"\bdefine\b",
    r"\bexplain\b",
    r"\btell me about\b",
    r"\bhow does\b",
    r"\bwhy does\b",
    r"\bdifference between\b",
    r"\bmeaning of\b",
    r"\bstand for\b",
]


def _matches(text: str, patterns: list[str]) -> int:
    """Return count of pattern matches (used as a weighted signal score)."""
    count = 0
    text_lower = text.lower()
    for pat in patterns:
        if re.search(pat, text_lower):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_BASE_PERSONA = """You are a helpful AI assistant for Ramblin' Repairs, a student-focused \
computer repair service. You are knowledgeable, friendly, and concise. \
Never make up prices or repair timelines — if you don't know, say so and \
suggest contacting support directly."""


PROMPT_TEMPLATES: dict[str, str] = {
    INTENT_FACTUAL_LOOKUP: _BASE_PERSONA
    + """

Your task for this message is a FACTUAL LOOKUP.
- Provide a clear, accurate answer to the user's question.
- Use the FAQ knowledge base as your primary source.
- If the FAQ doesn't cover it, use your general technical knowledge.
- Name which FAQ topic informed your answer when relevant.
- Keep the answer concise: 2–4 sentences unless depth is truly needed.
- Do NOT offer detailed repair steps or order status unless explicitly asked.
""",
    INTENT_REPAIR_GUIDANCE: _BASE_PERSONA
    + """

Your task for this message is REPAIR GUIDANCE.
- Walk the user through a repair or replacement procedure step-by-step; be very specific.
- Use iFixit guide content as your primary technical reference; use the exact steps from the guide, in the same order, and name the guide when relevant.
- Do NOT paste iFixit URLs in your reply.
- Reference the user's device type and order history to tailor the advice.
- Warn the user if the repair voids warranties or requires professional tools.
- End with: "Would you like us to handle this repair for you?"
""",
    INTENT_ORDER_STATUS: _BASE_PERSONA
    + """

Your task for this message is an ORDER STATUS inquiry.
- Reference the user's current and recent orders directly.
- State the order ID, device, issue summary, and current status clearly.
- If the order is in progress, mention what the next step typically is.
- If you cannot find the specific order, tell the user and suggest they \
contact support with their order ID.
- Do NOT speculate about timelines you don't have data for.
""",
    INTENT_TROUBLESHOOT: _BASE_PERSONA
    + """

Your task for this message is TROUBLESHOOTING.
- Ask one targeted clarifying question if critical info is missing \
(e.g., OS version, when the issue started).
- Provide a structured diagnostic approach: most-likely cause first, \
then alternatives.
- Use iFixit guide content and the FAQ to support your suggestions; do NOT paste iFixit URLs.
- Reference the user's device/order context if it's relevant.
- End with a clear recommendation: DIY fix, bring it in, or monitor.
""",
    INTENT_GENERAL_SUPPORT: _BASE_PERSONA
    + """

Your task for this message is GENERAL SUPPORT.
- Answer the user's question as helpfully as possible.
- Use the FAQ knowledge base for any policy or service questions.
- If the question is outside your scope, direct the user to contact \
Ramblin' Repairs support.
- Keep the tone warm and professional.
""",
}


def _parse_llm_intent(raw: str) -> Optional[str]:
    """Map free-form LLM output to a known intent constant."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-]+", "_", raw.strip().lower().strip("\"'"))
    if cleaned in ALL_INTENTS:
        return cleaned
    for intent in ALL_INTENTS:
        if intent in cleaned:
            return intent
    return None


def _classify_with_llm(message: str, recent_intent: Optional[str]) -> Optional[str]:
    # Use flexible API key selection like in llm_handler.py
    keys = getattr(settings, "OPENROUTER_API_KEYS", None)
    if not keys or not isinstance(keys, (list, tuple)) or len(keys) == 0:
        raise ValueError("OPENROUTER_API_KEYS is missing or empty in settings")

    # Determine active key index from DB (APIKeyConfig). Fall back to index 0 on any error.
    try:
        idx = APIKeyConfig.get_active_index()
        if not isinstance(idx, int) or idx < 0 or idx >= len(keys):
            idx = 0
    except Exception:
        idx = 0

    api_key = keys[idx]
    if not api_key:
        raise ValueError(f"Selected OPENROUTER_API_KEY at index {idx} is empty")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    context = f"Previous intent: {recent_intent}" if recent_intent else "No previous context."
    response = client.chat.completions.create(
        model=settings.OPENROUTER_MODEL,
        max_tokens=10,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify the user's message into exactly one of these intents:\n"
                    "- troubleshoot\n"
                    "- repair_guidance\n"
                    "- order_status\n"
                    "- factual_lookup\n"
                    "- general_support\n\n"
                    "Reply with ONLY the intent word, nothing else.\n"
                    f"{context}"
                ),
            },
            {"role": "user", "content": message},
        ],
    )
    raw = response.choices[0].message.content
    if raw is None:
        return None
    print(f"[Classifier] Raw intent guess: '{raw}', from model {response.model}", flush=True)
    return _parse_llm_intent(raw)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def classify_intent(
    message: str,
    has_active_order: bool = False,
    recent_intent: Optional[str] = None,
) -> RoutingResult:
    try:
        intent = _classify_with_llm(message, recent_intent)
        if not intent:
            raise ValueError("No valid intent from LLM")
        print(f"[Classifier] LLM intent='{intent}'", flush=True)
        return _build_result(intent, confidence="high")
    except Exception as e:
        print(f"[Classifier] FAILED: {e}, falling back to keywords", flush=True)
        return _classify_keywords_fallback(message, recent_intent, has_active_order)


def _classify_keywords_fallback(
    message: str,
    recent_intent: Optional[str],
    has_active_order: bool,
) -> RoutingResult:
    scores = {i: 0 for i in ALL_INTENTS}
    scores[INTENT_ORDER_STATUS] += _matches(message, _ORDER_STATUS_SIGNALS)
    scores[INTENT_TROUBLESHOOT] += _matches(message, _TROUBLESHOOT_SIGNALS)
    scores[INTENT_REPAIR_GUIDANCE] += _matches(message, _REPAIR_GUIDANCE_SIGNALS)
    scores[INTENT_FACTUAL_LOOKUP] += _matches(message, _FACTUAL_LOOKUP_SIGNALS)

    if has_active_order:
        scores[INTENT_ORDER_STATUS] += 1

    if scores[INTENT_REPAIR_GUIDANCE] > 0:
        scores[INTENT_REPAIR_GUIDANCE] += 2

    top = max(scores, key=lambda k: scores[k])
    if scores[top] == 0:
        fallback = (
            recent_intent if recent_intent in ALL_INTENTS else INTENT_TROUBLESHOOT
        )
        return _build_result(fallback, confidence="low")

    return _build_result(top, confidence="medium")


def _build_result(intent: str, confidence: str = "high") -> RoutingResult:
    """Map an intent to its full RoutingResult with source flags."""
    resolved = intent if intent in PROMPT_TEMPLATES else INTENT_GENERAL_SUPPORT

    config = {
        INTENT_FACTUAL_LOOKUP: dict(
            use_faq=True,
            use_ifixit=False,
            use_order_context=False,
            sources_label="FAQ Knowledge Base",
        ),
        INTENT_REPAIR_GUIDANCE: dict(
            use_faq=True,
            use_ifixit=True,
            use_order_context=True,
            sources_label="iFixit Guides, FAQ Knowledge Base, Your Order History",
        ),
        INTENT_ORDER_STATUS: dict(
            use_faq=False,
            use_ifixit=False,
            use_order_context=True,
            sources_label="Your Order History",
        ),
        INTENT_TROUBLESHOOT: dict(
            use_faq=True,
            use_ifixit=True,
            use_order_context=True,
            sources_label="iFixit Guides, FAQ Knowledge Base, Your Order History",
        ),
        INTENT_GENERAL_SUPPORT: dict(
            use_faq=True,
            use_ifixit=False,
            use_order_context=False,
            sources_label="FAQ Knowledge Base",
        ),
    }

    cfg = config.get(resolved, config[INTENT_GENERAL_SUPPORT])
    return RoutingResult(
        intent=resolved,
        system_prompt=PROMPT_TEMPLATES[resolved],
        confidence=confidence,
        **cfg,
    )
