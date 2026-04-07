from __future__ import annotations

from django.db import models


class ChatSession(models.Model):
    user_id = models.CharField(max_length=255, db_index=True)
    course_topic = models.ForeignKey(
        "chat_api.CourseTopic",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"ChatSession(user_id={self.user_id!r}, course_topic_id={self.course_topic_id!r}, id={self.pk})"


class ChatTurn(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="turns")
    prompt_key = models.CharField(max_length=100)
    user_text = models.TextField()
    agent_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"ChatTurn(session_id={self.session_id}, prompt_key={self.prompt_key!r}, id={self.pk})"


class ChatContext(models.Model):
    session = models.OneToOneField(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="context",
    )
    compacted_through_turn = models.ForeignKey(
        ChatTurn,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    summary = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_compacted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("session_id",)

    def __str__(self) -> str:
        return f"ChatContext(session_id={self.session_id})"
