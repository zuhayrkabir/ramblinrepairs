from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('send/', views.chat_handler, name='chat_send'),
    path('history/', views.chat_history, name='chat_history'),
    path('clear/', views.clear_chat_history, name='clear_chat_history'),
]