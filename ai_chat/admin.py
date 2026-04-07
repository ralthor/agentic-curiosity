from django.contrib import admin

from chat_api.course_state import serialize_course_state

from .models import ChatContext, ChatSession, ChatTurn


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "course_topic", "course_progress", "created_at", "updated_at")
    list_select_related = ("course_topic",)
    search_fields = ("user_id", "course_topic__name")
    ordering = ("-created_at", "-id")

    @admin.display(description="Progress")
    def course_progress(self, obj: ChatSession) -> str:
        state = serialize_course_state(
            obj.course_state,
            expectations=obj.course_topic.expectations if obj.course_topic is not None else None,
        )
        return f"{state['overall_progress']}%"


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
