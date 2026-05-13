from django.contrib import admin
from .models import ChatUsageLog


@admin.register(ChatUsageLog)
class ChatUsageLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'query', 'response_time_ms', 'model', 'status', 'timestamp')
    list_filter = ('status', 'timestamp', 'user', 'model')
    search_fields = ('query', 'user__username', 'model')
    readonly_fields = ('timestamp',)
