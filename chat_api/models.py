from __future__ import annotations

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def generate_api_token_key() -> str:
    return secrets.token_hex(32)


class Course(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")

    def __str__(self) -> str:
        return self.name


class CourseTopic(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="topics",
    )
    name = models.CharField(max_length=255)
    import_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("course_id", "name", "id")
        constraints = [
            models.UniqueConstraint(fields=("course", "name"), name="chat_api_course_topic_unique_name"),
        ]

    def __str__(self) -> str:
        return f"{self.course.name}: {self.name}"


class QuestionType(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="question_types",
    )
    name = models.CharField(max_length=255)
    hint_prompt = models.TextField()
    mark_prompt = models.TextField()
    import_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("course_id", "name", "id")
        constraints = [
            models.UniqueConstraint(fields=("course", "name"), name="chat_api_question_type_unique_name"),
        ]

    def __str__(self) -> str:
        return f"{self.course.name}: {self.name}"


class CourseQuestion(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    topic = models.ForeignKey(
        CourseTopic,
        on_delete=models.PROTECT,
        related_name="questions",
    )
    question_type = models.ForeignKey(
        QuestionType,
        on_delete=models.PROTECT,
        related_name="questions",
    )
    question_text = models.TextField()
    max_marks = models.PositiveIntegerField()
    sample_answer = models.TextField(blank=True, default="")
    marking_notes = models.TextField(blank=True, default="")
    import_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("course_id", "topic_id", "id")

    def __str__(self) -> str:
        return f"Question {self.pk} ({self.course.name})"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.max_marks <= 0:
            errors["max_marks"] = "max_marks must be greater than zero."
        if self.topic_id and self.course_id and self.topic.course_id != self.course_id:
            errors["topic"] = "topic must belong to the same course as the question."
        if self.question_type_id and self.course_id and self.question_type.course_id != self.course_id:
            errors["question_type"] = "question_type must belong to the same course as the question."
        if errors:
            raise ValidationError(errors)


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
