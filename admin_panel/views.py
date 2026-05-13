from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Count, Q
from datetime import timedelta
from django.utils import timezone

from FAQ.models import FAQ

from .models import ChatUsageLog, APIKeyConfig
from .forms import APIKeyConfigForm, FAQFormSet


@staff_member_required
def admin_dashboard(request):
    """Display system performance metrics, usage logs, and API key selection."""
    
    # Handle API key selection form submission
    if request.method == "POST" and "select_api_key" in request.POST:
        form = APIKeyConfigForm(request.POST)
        if form.is_valid():
            # Get or create the singleton APIKeyConfig record
            config, _ = APIKeyConfig.objects.get_or_create(pk=1)
            config.active_key_index = form.cleaned_data['active_key_index']
            config.save()
            # Redirect to clear the form data on page reload
            return redirect("admin_panel:dashboard")
    else:
        # Load existing configuration
        config = APIKeyConfig.objects.filter(pk=1).first()
        if config:
            # Convert to string since form choices are strings
            form = APIKeyConfigForm(initial={'active_key_index': str(config.active_key_index)})
        else:
            form = APIKeyConfigForm()
    
    # Calculate performance metrics (last 7 days)
    twenty_four_hours_ago = timezone.now() - timedelta(days=7)
    recent_logs = ChatUsageLog.objects.filter(timestamp__gte=twenty_four_hours_ago)
    
    # Calculate average latency and failure rate
    avg_latency = recent_logs.aggregate(Avg('response_time_ms'))['response_time_ms__avg'] or 0
    total_requests = recent_logs.count()
    failed_requests = recent_logs.filter(~Q(status='success')).count()
    failure_rate = (failed_requests / total_requests * 100) if total_requests > 0 else 0
    
    performance_data = {
        "latency_ms": round(avg_latency, 2),
        "failure_rate": round(failure_rate, 2),
        "total_requests": total_requests,
    }

    # Get recent usage logs (last few) with model information
    usage_logs_qs = ChatUsageLog.objects.all()[:100]
    logs_data = [
        {
            "query": log.query[:60] + "..." if len(log.query) > 60 else log.query,
            "timestamp": log.timestamp.strftime("%Y-%m-%d %I:%M %p"),
            "response_time_ms": log.response_time_ms,
            "status": log.get_status_display(),
            "model": log.model or "N/A",
        }
        for log in usage_logs_qs
    ]

    context = {
        "performance_data": performance_data,
        "usage_logs": logs_data,
        "api_key_form": form,
    }

    return render(request, "admin_panel/dashboard.html", context)


@staff_member_required
def manage_faqs(request):
    """Add / edit / delete entries in the FAQ knowledge base.

    Implements the admin user story: "manually clear or reload the chatbot's
    knowledge base". The FAQ table is the curated portion of the chatbot's
    knowledge base, so editing it here directly updates the data the RAG
    pipeline injects into the LLM prompt (see ``chat.llm_handler.get_faq_context``).
    """
    queryset = FAQ.objects.all()

    if request.method == "POST":
        formset = FAQFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            instances = formset.save(commit=False)
            # Auto-assign display order for any brand-new FAQ so it lands at
            # the bottom of the list. Existing FAQs keep their current order.
            current_max = (
                FAQ.objects.order_by("-order").values_list("order", flat=True).first() or 0
            )
            next_order = current_max + 10
            for obj in instances:
                if obj.pk is None and (obj.order is None or obj.order == 0):
                    obj.order = next_order
                    next_order += 10
                obj.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(
                request,
                "FAQ knowledge base updated. Changes are live for the chatbot.",
            )
            return redirect("admin_panel:manage_faqs")
        messages.error(
            request,
            "Could not save FAQs. Please fix the highlighted errors and try again.",
        )
    else:
        formset = FAQFormSet(queryset=queryset)

    return render(
        request,
        "admin_panel/manage_faqs.html",
        {
            "formset": formset,
            "faq_count": queryset.count(),
        },
    )