from __future__ import annotations

from django.db import models
from django.utils import timezone


class ChatSession(models.Model):
    user_id = models.CharField(max_length=255, db_index=True)
    course = models.ForeignKey(
        "chat_api.Course",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    active_presentation = models.ForeignKey(
        "QuestionPresentation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    selector_override_topic = models.ForeignKey(
        "chat_api.CourseTopic",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="selector_override_sessions",
    )
    selector_override_question = models.ForeignKey(
        "chat_api.CourseQuestion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="selector_override_sessions",
    )
    selector_strategy_override = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"ChatSession(user_id={self.user_id!r}, course_id={self.course_id!r}, id={self.pk})"


class QuestionPresentation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"
        ABANDONED = "abandoned", "Abandoned"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="presentations")
    question = models.ForeignKey(
        "chat_api.CourseQuestion",
        on_delete=models.PROTECT,
        related_name="presentations",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    selection_source = models.CharField(max_length=50, blank=True, default="selector")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("opened_at", "id")

    def __str__(self) -> str:
        return f"QuestionPresentation(session_id={self.session_id}, question_id={self.question_id}, status={self.status!r})"


class QuestionAttempt(models.Model):
    class InteractionType(models.TextChoices):
        HINT_REQUEST = "hint_request", "Hint Request"
        ANSWER_ATTEMPT = "answer_attempt", "Answer Attempt"
        SKIP = "skip", "Skip"

    presentation = models.ForeignKey(
        QuestionPresentation,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    interaction_type = models.CharField(max_length=20, choices=InteractionType.choices)
    student_message = models.TextField()
    model_response_text = models.TextField(blank=True, default="")
    awarded_marks = models.PositiveIntegerField(null=True, blank=True)
    derived_leitner_score = models.PositiveSmallIntegerField(null=True, blank=True)
    completed_presentation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"QuestionAttempt(presentation_id={self.presentation_id}, interaction_type={self.interaction_type!r}, id={self.pk})"


class LearnerQuestionState(models.Model):
    user_id = models.CharField(max_length=255, db_index=True)
    course = models.ForeignKey(
        "chat_api.Course",
        on_delete=models.CASCADE,
        related_name="learner_question_states",
    )
    question = models.ForeignKey(
        "chat_api.CourseQuestion",
        on_delete=models.CASCADE,
        related_name="learner_states",
    )
    latest_leitner_score = models.PositiveSmallIntegerField(default=0)
    best_leitner_score = models.PositiveSmallIntegerField(default=0)
    due_at = models.DateTimeField(default=timezone.now)
    times_seen = models.PositiveIntegerField(default=0)
    times_answered = models.PositiveIntegerField(default=0)
    last_presented_at = models.DateTimeField(null=True, blank=True)
    last_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user_id", "course_id", "question_id")
        constraints = [
            models.UniqueConstraint(
                fields=("user_id", "course", "question"),
                name="ai_chat_unique_learner_question_state",
            ),
        ]

    def __str__(self) -> str:
        return f"LearnerQuestionState(user_id={self.user_id!r}, question_id={self.question_id}, latest={self.latest_leitner_score})"
