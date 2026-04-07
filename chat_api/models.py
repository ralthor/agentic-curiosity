from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models


def generate_api_token_key() -> str:
    return secrets.token_hex(32)


class CourseTopic(models.Model):
    name = models.CharField(max_length=255, unique=True)
    teacher_prompt = models.TextField()
    judge_prompt = models.TextField()
    categorizer_prompt = models.TextField()
    answerer_prompt = models.TextField()
    planner_prompt = models.TextField()
    briefer_prompt = models.TextField()
    expectations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")

    def __str__(self) -> str:
        return self.name


class ApiToken(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_token",
    )
    key = models.CharField(max_length=64, unique=True, default=generate_api_token_key, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user_id",)

    def __str__(self) -> str:
        return f"ApiToken(user_id={self.user_id})"

    @classmethod
    def issue_for_user(cls, user) -> "ApiToken":
        token, created = cls.objects.get_or_create(user=user)
        if created and token.key:
            return token

        if not token.key:
            token.key = generate_api_token_key()
            token.save(update_fields=["key", "updated_at"])
        return token
