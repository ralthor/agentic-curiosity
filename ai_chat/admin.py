from django.contrib import admin

from .models import ChatContext, ChatSession, ChatTurn


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "course_topic", "created_at", "updated_at")
    list_select_related = ("course_topic",)
    search_fields = ("user_id", "course_topic__name")
    ordering = ("-created_at", "-id")


@admin.register(ChatTurn)
class ChatTurnAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "prompt_key", "created_at")
    list_filter = ("prompt_key",)
    search_fields = ("session__user_id", "user_text", "agent_response")
    ordering = ("-created_at", "-id")


@admin.register(ChatContext)
class ChatContextAdmin(admin.ModelAdmin):
    list_display = ("session", "compacted_through_turn", "last_compacted_at", "updated_at")
    search_fields = ("session__user_id", "summary")
    ordering = ("session_id",)
