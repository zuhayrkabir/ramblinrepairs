from django.urls import path
from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.admin_dashboard, name="dashboard"),
    path("faqs/", views.manage_faqs, name="manage_faqs"),
]
