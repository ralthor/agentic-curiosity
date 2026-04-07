from __future__ import annotations

from django.db import models


class ChatSession(models.Model):
    user_id = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"ChatSession(user_id={self.user_id!r}, id={self.pk})"


class ChatTurn(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="turns")
    prompt_key = models.CharField(max_length=100)
    user_text = models.TextField()
    agent_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"ChatTurn(session_id={self.session_id}, prompt_key={self.prompt_key!r}, id={self.pk})"


class ChatContext(models.Model):
    user_id = models.CharField(max_length=255, unique=True)
    current_session = models.ForeignKey(
        ChatSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    compacted_through_turn = models.ForeignKey(
        ChatTurn,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    summary = models.TextField(blank=True, default="")
    last_compacted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user_id",)

    def __str__(self) -> str:
        return f"ChatContext(user_id={self.user_id!r})"
