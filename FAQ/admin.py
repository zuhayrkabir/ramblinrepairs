from django.contrib import admin

from .models import FAQ


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("order", "question")
    list_editable = ("question",)
    ordering = ("order", "question")
    search_fields = ("question", "answer")
