from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path("new/", views.order_create, name="order_create"),
    path("mine/", views.my_orders, name="my_orders"),
    path("<int:order_id>/", views.order_detail, name="order_detail"),
    path("<int:order_id>/delete/", views.order_delete, name="order_delete"),
]