from django.contrib import admin

from .models import AnswerPhotoUpload, ChatSession, LearnerQuestionState, QuestionAttempt, QuestionPresentation


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "course", "active_presentation", "created_at", "updated_at")
    list_select_related = ("course", "active_presentation")
    search_fields = ("user_id", "course__name")
    ordering = ("-created_at", "-id")


@admin.register(QuestionPresentation)
class QuestionPresentationAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "question", "status", "selection_source", "opened_at", "closed_at")
    list_select_related = ("session", "question")
    list_filter = ("status", "selection_source")
    search_fields = ("session__user_id", "question__question_text")
    ordering = ("-opened_at", "-id")


@admin.register(QuestionAttempt)
class QuestionAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "presentation",
        "interaction_type",
        "awarded_marks",
        "derived_leitner_score",
        "completed_presentation",
        "created_at",
    )
    list_filter = ("interaction_type", "completed_presentation")
    search_fields = ("presentation__session__user_id", "student_message", "model_response_text")
    ordering = ("-created_at", "-id")


@admin.register(LearnerQuestionState)
class LearnerQuestionStateAdmin(admin.ModelAdmin):
    list_display = (
        "user_id",
        "course",
        "question",
        "latest_leitner_score",
        "best_leitner_score",
        "due_at",
        "times_seen",
        "times_answered",
    )
    list_select_related = ("course", "question")
    search_fields = ("user_id", "course__name", "question__question_text")
    ordering = ("user_id", "course__name", "question_id")


@admin.register(AnswerPhotoUpload)
class AnswerPhotoUploadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "presentation",
        "attempt",
        "filename",
        "content_type",
        "byte_size",
        "display_order",
        "created_at",
    )
    list_select_related = ("session", "presentation", "attempt")
    list_filter = ("content_type",)
    search_fields = ("session__user_id", "filename", "storage_key", "extracted_text")
    ordering = ("-created_at", "-id")
