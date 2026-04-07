from django.contrib import admin

from .models import ChatContext, ChatSession, ChatTurn


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "created_at", "updated_at")
    search_fields = ("user_id",)
    ordering = ("-created_at", "-id")


@admin.register(ChatTurn)
class ChatTurnAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "prompt_key", "created_at")
    list_filter = ("prompt_key",)
    search_fields = ("session__user_id", "user_text", "agent_response")
    ordering = ("-created_at", "-id")


@admin.register(ChatContext)
class ChatContextAdmin(admin.ModelAdmin):
    list_display = ("user_id", "current_session", "compacted_through_turn", "last_compacted_at", "updated_at")
    search_fields = ("user_id", "summary")
    ordering = ("user_id",)
