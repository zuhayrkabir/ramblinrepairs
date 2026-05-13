from django.db import models
from django.contrib.auth.models import User
from orders.models import Order


class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message_text = models.TextField()
    sender = models.CharField(max_length=10, choices=[('user', 'User'), ('bot', 'Bot')])
    timestamp = models.DateTimeField(auto_now_add=True)
    order_context = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    # Optional source metadata for retrieval-augmented responses
    source_url = models.URLField(max_length=2048, null=True, blank=True)
    source_title = models.CharField(max_length=255, null=True, blank=True)
    source_text = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender}: {self.message_text[:50]}"
