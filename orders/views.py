from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.contrib import messages


from .forms import OrderCreateForm
from .models import Order


@login_required
def order_create(request):
    """
    User submits a new repair ticket.
    Admin-only fields (status, pricing, timestamps) are not user-editable.
    """
    if request.method == "POST":
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.user = request.user          # attach the logged-in user
            order.status = "submitted"         # ensure default workflow state
            order.save()
            return redirect("orders:order_detail", order_id=order.id)
    else:
        # Pre-fill contact email from the logged-in account if it's available
        initial = {}
        if request.user.email:
            initial["contact_email"] = request.user.email
        form = OrderCreateForm(initial=initial)

    return render(request, "orders/order_create.html", {"form": form})


@login_required
def my_orders(request):
    """
    Shows the logged-in user's own tickets.
    """
    orders = (
        Order.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )
    return render(request, "orders/my_orders.html", {"orders": orders})


@login_required
def order_detail(request, order_id):
    """
    Shows a single ticket.
    Users can only view their own ticket unless they're staff.
    """
    order = get_object_or_404(Order, id=order_id)

    if (order.user != request.user) and (not request.user.is_staff):
        return HttpResponseForbidden("You do not have permission to view this order.")

    return render(request, "orders/order_detail.html", {"order": order, "order_id": order_id})

@login_required
def order_delete(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # Only the owner can delete (or staff if you want)
    if order.user != request.user and not request.user.is_staff:
        return HttpResponseForbidden("You do not have permission to delete this ticket.")

    if request.method == "POST":
        order.delete()
        messages.success(request, "Your ticket was deleted.")
        return redirect("orders:my_orders")

    # GET -> show confirmation page
    return render(request, "orders/order_confirm_delete.html", {"order": order})
