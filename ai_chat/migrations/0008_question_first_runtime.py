from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def backfill_session_course(apps, schema_editor):
    ChatSession = apps.get_model("ai_chat", "ChatSession")
    Course = apps.get_model("chat_api", "Course")

    fallback_course = Course.objects.order_by("id").first()
    if fallback_course is None and ChatSession.objects.filter(course__isnull=True).exists():
        fallback_course = Course.objects.create(name="Migrated Course")

    if fallback_course is not None:
        ChatSession.objects.filter(course__isnull=True).update(course=fallback_course)


class Migration(migrations.Migration):
    dependencies = [
        ("chat_api", "0007_question_first_course_engine"),
        ("ai_chat", "0007_backfill_chatsession_course_state"),
    ]

    operations = [
        migrations.RenameField(
            model_name="chatsession",
            old_name="course_topic",
            new_name="course",
        ),
        migrations.RunPython(backfill_session_course, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="chatsession",
            name="course",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sessions", to="chat_api.course"),
        ),
        migrations.RemoveField(
            model_name="chatsession",
            name="course_state",
        ),
        migrations.CreateModel(
            name="QuestionPresentation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("active", "Active"), ("completed", "Completed"), ("skipped", "Skipped"), ("abandoned", "Abandoned")], default="active", max_length=20)),
                ("selection_source", models.CharField(blank=True, default="selector", max_length=50)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "question",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="presentations", to="chat_api.coursequestion"),
                ),
                (
                    "session",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="presentations", to="ai_chat.chatsession"),
                ),
            ],
            options={
                "ordering": ("opened_at", "id"),
            },
        ),
        migrations.AddField(
            model_name="chatsession",
            name="active_presentation",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="ai_chat.questionpresentation"),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="selector_override_question",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="selector_override_sessions", to="chat_api.coursequestion"),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="selector_override_topic",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="selector_override_sessions", to="chat_api.coursetopic"),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="selector_strategy_override",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.CreateModel(
            name="QuestionAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("interaction_type", models.CharField(choices=[("hint_request", "Hint Request"), ("answer_attempt", "Answer Attempt"), ("skip", "Skip")], max_length=20)),
                ("student_message", models.TextField()),
                ("model_response_text", models.TextField(blank=True, default="")),
                ("awarded_marks", models.PositiveIntegerField(blank=True, null=True)),
                ("derived_leitner_score", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("completed_presentation", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "presentation",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="ai_chat.questionpresentation"),
                ),
            ],
            options={
                "ordering": ("created_at", "id"),
            },
        ),
        migrations.CreateModel(
            name="LearnerQuestionState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.CharField(db_index=True, max_length=255)),
                ("latest_leitner_score", models.PositiveSmallIntegerField(default=0)),
                ("best_leitner_score", models.PositiveSmallIntegerField(default=0)),
                ("due_at", models.DateTimeField(default=timezone.now)),
                ("times_seen", models.PositiveIntegerField(default=0)),
                ("times_answered", models.PositiveIntegerField(default=0)),
                ("last_presented_at", models.DateTimeField(blank=True, null=True)),
                ("last_completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="learner_question_states", to="chat_api.course"),
                ),
                (
                    "question",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="learner_states", to="chat_api.coursequestion"),
                ),
            ],
            options={
                "ordering": ("user_id", "course_id", "question_id"),
            },
        ),
        migrations.AddConstraint(
            model_name="learnerquestionstate",
            constraint=models.UniqueConstraint(fields=("user_id", "course", "question"), name="ai_chat_unique_learner_question_state"),
        ),
        migrations.DeleteModel(
            name="ChatContext",
        ),
        migrations.DeleteModel(
            name="ChatTurn",
        ),
    ]
