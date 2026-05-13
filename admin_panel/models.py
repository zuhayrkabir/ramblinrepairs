from django.db import models
from django.contrib.auth.models import User


class ChatUsageLog(models.Model):
    """Tracks performance metrics for each chatbot interaction."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.TextField()  # The user's query
    response_time_ms = models.IntegerField()  # Time taken to generate response
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('failure', 'Failure'),
            ('error', 'Error'),
        ],
        default='success'
    )
    error_message = models.TextField(null=True, blank=True)  # Error details if failed
    model = models.CharField(max_length=255, null=True, blank=True)  # LLM model used
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username} - {self.status} - {self.response_time_ms}ms"


class APIKeyConfig(models.Model):
    """Stores which OpenRouter API key index is active for runtime selection."""
    # Keep as a single-row config; admin UI prevents creating multiple records.
    active_key_index = models.IntegerField(default=0)

    @classmethod
    def get_active_index(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj.active_key_index

    def __str__(self):
        return f"Active key index: {self.active_key_index}"
