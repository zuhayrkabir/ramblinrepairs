from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import traceback
import time

from .llm_handler import get_chatbot_response
from admin_panel.models import ChatUsageLog


@login_required
@csrf_exempt
@require_POST
def chat_handler(request):
    """Handle chat messages and return bot responses."""
    start_time = time.time()
    
    try:
        raw_body = request.body.decode("utf-8")
        print("RAW REQUEST BODY:", raw_body, flush=True)

        data = json.loads(raw_body)
        message = data.get("message", "")
        order_id = data.get("order_id")

        if not isinstance(message, str):
            return JsonResponse({"error": "Message must be a string"}, status=400)

        message = message.strip()

        print(f"PARSED MESSAGE: {message}", flush=True)
        print(f"PARSED ORDER ID: {order_id}", flush=True)

        if not message:
            return JsonResponse({"error": "Message cannot be empty"}, status=400)

        recent_intent = request.session.get("chat_last_intent")
        response, intent, source_url, source_title = get_chatbot_response(
            request.user, message, order_id, recent_intent=recent_intent
        )
        if intent:
            request.session["chat_last_intent"] = intent


        payload = {"response": response, "status": "success"}
        if intent:
            payload["intent"] = intent
        if source_url:
            payload["source_url"] = source_url
        if source_title:
            payload["source_title"] = source_title

        return JsonResponse(payload)

    except json.JSONDecodeError:
        print("JSONDecodeError while parsing request body", flush=True)
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    except Exception as e:
        print("ERROR IN chat_handler:", str(e), flush=True)
        print(traceback.format_exc(), flush=True)
        try:
            message_text = ""
            try:
                message_text = json.loads(raw_body).get("message", "")
            except:
                pass
        except:
            pass  # If logging fails, don't crash
        return JsonResponse({
            "error": "Internal server error",
            "details": str(e)
        }, status=500)


@login_required
def chat_history(request):
    """Return user's chat history as JSON."""
    from .models import ChatMessage

    messages = ChatMessage.objects.filter(user=request.user).order_by('-timestamp')[:50]
    messages = list(messages)[::-1]

    history = []
    for msg in messages:
        history.append({
            'message': msg.message_text,
            'sender': msg.sender,
            'timestamp': msg.timestamp.isoformat(),
            'source_url': getattr(msg, 'source_url', None),
            'source_title': getattr(msg, 'source_title', None),
            'source_text': (getattr(msg, 'source_text', None)[:1000] if getattr(msg, 'source_text', None) else None),
        })

    return JsonResponse({
        'history': history,
        'status': 'success'
    })


@login_required
@csrf_exempt
@require_POST
def clear_chat_history(request):
    """Clear all chat history for the current user."""
    from .models import ChatMessage

    try:
        ChatMessage.objects.filter(user=request.user).delete()
        return JsonResponse({
            'status': 'success',
            'message': 'Chat history cleared successfully'
        })
    except Exception as e:
        print("ERROR IN clear_chat_history:", str(e), flush=True)
        return JsonResponse({
            'status': 'error',
            'message': 'Failed to clear chat history'
        }, status=500)