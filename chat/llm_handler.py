import re
import sys
import traceback

from django.conf import settings
from openai import OpenAI

from .models import ChatMessage
from orders.models import Order
from FAQ.models import FAQ
from .ifixit_service import get_ifixit_context, is_repair_related_message
from .prompt_router import classify_intent


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(value):
    """Best-effort plain-text version of an FAQ answer for LLM consumption.

    FAQ answers may be authored in plain text or contain light HTML markup
    (bullet lists, <kbd>, <strong>, etc.). The chat model does not need the
    markup, so we strip tags and collapse whitespace before injecting them
    into the system prompt.
    """
    if not isinstance(value, str):
        return ""
    no_tags = _HTML_TAG_RE.sub(" ", value)
    return _WHITESPACE_RE.sub(" ", no_tags).strip()


from admin_panel.models import ChatUsageLog, APIKeyConfig
import time


UNIVERSAL_FORMATTING = """
Formatting rules:
- Use short bullet points or numbered lists for steps, never tables
- Keep lines short so they fit in a narrow chat widget
- Do not use markdown tables, horizontal rules, or multi-column layouts
- Bold only key terms sparingly; avoid excessive formatting
- End lines with a newline character; use double newlines no more than rarely
- Place URLs on their own line if you include them

"""

IFIXIT_CONTEXT_RULES = """
When iFixit guide content appears below:
- Relay its information faithfully; do NOT invent or change specific details (steps, colors, numbers)
- Present steps concisely, but every fact must come from the provided content, in the same order as the source
- If no device-specific content was found, say your advice is general
- Do NOT include iFixit URLs in your response

"""

SCOPE_BOUNDARIES = """
Scope & Boundaries:
- You ONLY assist with topics related to computer repair, troubleshooting, device issues, and Ramblin' Repairs services.
- Relevant topics: hardware problems, software issues, device repair guidance, order status, pricing, service hours, general tech support.
- Off-topic topics: homework, finance advice, medical questions, legal questions, politics, unrelated tech support, general chat.
- When a question is clearly outside your scope, respond politely: "I'm specifically trained to help with computer repair and Ramblin' Repairs services. Your question is outside my area—I'd recommend [relevant resource] instead."
- If unsure whether a topic is relevant, err toward being helpful but note your limitations.

"""


def get_openai_client():
    # Expect a list of API keys in settings
    keys = getattr(settings, "OPENROUTER_API_KEYS", None)
    if not keys or not isinstance(keys, (list, tuple)) or len(keys) == 0:
        raise ValueError("OPENROUTER_API_KEYS is missing or empty in settings")

    if not getattr(settings, "OPENROUTER_MODEL", None):
        raise ValueError("OPENROUTER_MODEL is missing from settings")

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

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )


def safe_text(value):
    return value.strip() if isinstance(value, str) else ""


def get_faq_context():
    faqs = FAQ.objects.all()
    context = "FAQ Knowledge Base:\n"
    for faq in faqs:
        question = _strip_html(safe_text(faq.question))
        answer = _strip_html(safe_text(faq.answer))
        if not question and not answer:
            continue
        context += f"Q: {question}\nA: {answer}\n\n"
    return context


def get_user_order_context(user, current_order_id=None):
    """
    Safe even when the user has no orders.
    """
    context = "User's Repair History:\n"

    if current_order_id:
        try:
            current_order = Order.objects.get(id=current_order_id, user=user)
            context += f"Current Active Order (ID: {current_order.id}):\n"
            context += f"- Device: {safe_text(current_order.device_type)}\n"
            context += f"- Issue: {safe_text(current_order.issue_description)}\n"
            context += f"- Status: {safe_text(current_order.status)}\n"
            context += f"- Priority: {safe_text(current_order.priority)}\n"
            context += f"- Estimated Cost: {current_order.estimated_cost}\n\n"
        except Order.DoesNotExist:
            context += "No matching current order found.\n\n"

    recent_orders = Order.objects.filter(user=user).order_by("-created_at")[:5]

    if recent_orders.exists():
        context += "Recent Orders:\n"
        for order in recent_orders:
            if current_order_id and order.id == current_order_id:
                continue

            device_text = safe_text(order.device_type)
            issue_text = safe_text(order.issue_description)
            issue_preview = issue_text[:50] + ("..." if len(issue_text) > 50 else "")

            context += (
                f"- Order {order.id}: {device_text} - "
                f"{issue_preview} (Status: {safe_text(order.status)})\n"
            )
        context += "\n"
    else:
        context += "No prior repair orders found.\n\n"

    return context


def build_system_prompt(user, user_message, current_order_id=None, recent_intent=None):
    routing = classify_intent(
        safe_text(user_message),
        has_active_order=bool(current_order_id),
        recent_intent=recent_intent,
    )

    prompt_parts = [routing.system_prompt]
    prompt_parts.append(SCOPE_BOUNDARIES)
    if routing.use_ifixit:
        prompt_parts.append(IFIXIT_CONTEXT_RULES)
    prompt_parts.append(UNIVERSAL_FORMATTING)
    base_assembled = "".join(prompt_parts)

    faq_context = get_faq_context() if routing.use_faq else ""
    order_context = (
        get_user_order_context(user, current_order_id)
        if routing.use_order_context
        else ""
    )

    def _should_search_ifixit(msg: str) -> bool:
        """Heuristic to avoid unnecessary web searches for trivial replies.

        Rules:
        - If the message appears repair-related (via `is_repair_related_message`) -> search
        - If message contains a question mark or is reasonably long (>20 chars) -> search
        - Otherwise (short confirmations like "yes", "ok", "thanks") -> skip
        """
        txt = safe_text(msg)
        if not txt:
            return False
        low = txt.lower()
        # very short replies or common single-word confirmations
        trivial_tokens = {"yes", "no", "ok", "okay", "thanks", "thank you", "sure", "yep", "yup", "nah", "nope", "got it", "thanks!"}
        if low in trivial_tokens:
            return False
        if is_repair_related_message(txt):
            return True
        if "?" in txt:
            return True
        if len(txt) > 20:
            return True
        print("[iFixit] SKIPPING web search for \"trivial\" message:", flush=True)
        return False

    if routing.use_ifixit:
        if _should_search_ifixit(user_message):
            ifixit_result = get_ifixit_context(user, user_message, current_order_id)
        else:
            # Skip expensive web search for trivial messages
            ifixit_result = {
                "context": "iFixit Repair Knowledge:\nNot retrieved for this message (no search needed).\n\n",
                "source_url": "",
                "source_title": "",
            }
    else:
        ifixit_result = {
            "context": "iFixit Repair Knowledge:\nNot retrieved for this intent.\n\n",
            "source_url": "",
            "source_title": "",
        }

    ifixit_context = ifixit_result["context"]
    source_url = ifixit_result.get("source_url", "")
    source_title = ifixit_result.get("source_title", "")

    # Prefer iFixit technical content first, then FAQ, then user order context
    full_prompt = base_assembled + ifixit_context + order_context

    print(
        f"[Prompt] intent={routing.intent} confidence={routing.confidence} "
        f"faq={routing.use_faq} ifixit={routing.use_ifixit} orders={routing.use_order_context}",
        flush=True,
    )
    print("[Prompt] ---- BEGIN PROMPT ----", flush=True)
    print(full_prompt, flush=True)
    print("[Prompt] ---- END PROMPT ----", flush=True)

    return full_prompt, source_url, source_title, routing, ifixit_result


def get_chatbot_response(user, message, current_order_id=None, recent_intent=None):
    start_time = time.time()
    try:
        client = get_openai_client()
        system_prompt, source_url, source_title, routing, ifixit_result = build_system_prompt(
            user, message, current_order_id, recent_intent=recent_intent
        )

        recent_messages = ChatMessage.objects.filter(user=user).order_by("-timestamp")[:5]

        conversation_history = [{"role": "system", "content": system_prompt}]

        for msg in reversed(recent_messages):
            role = "user" if msg.sender == "user" else "assistant"
            conversation_history.append({"role": role, "content": msg.message_text or ""})

        conversation_history.append({"role": "user", "content": message or ""})

        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=conversation_history,
            temperature=0.
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        content = response.choices[0].message.content
        bot_response = content.strip() if isinstance(content, str) else "Sorry, I couldn't generate a response."
        bot_response = bot_response.replace("\n\n", "\n")

        ChatMessage.objects.create(
            user=user,
            message_text=message or "",
            sender="user",
            order_context_id=current_order_id
        )

        ChatMessage.objects.create(
            user=user,
            message_text=bot_response,
            sender="bot",
            order_context_id=current_order_id,
            source_url=source_url or None,
            source_title=source_title or None,
            source_text=ifixit_result.get("context") if isinstance(ifixit_result, dict) else None,
        )

        # Log usage for admin dashboard
        ChatUsageLog.objects.create(
            user=user,
            query=message or "",
            response_time_ms=response_time_ms,
            status='success',
            model=response.model,
        )

        print("\n[Response]", response.model, flush=True)
        print(bot_response, flush=True)
        print("======[END Response]======\n\n\n\n", flush=True)

        return bot_response, routing.intent, source_url or None, source_title or None

    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        print("ERROR IN get_chatbot_response:", str(e), flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)

        ChatMessage.objects.create(
            user=user,
            message_text=message or "",
            sender="user",
            order_context_id=current_order_id
        )

        # Log failure
        ChatUsageLog.objects.create(
            user=user,
            query=message or "",
            response_time_ms=response_time_ms,
            status='failure',
            error_message=str(e),
        )

        return f"Backend error: {str(e)}", None, None, None