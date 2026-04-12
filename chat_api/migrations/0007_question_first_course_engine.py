from __future__ import annotations

import re

from django.db import migrations, models


_EXPECTATION_PREFIX_RE = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)")


def migrate_expectations_to_topics(apps, schema_editor):
    Course = apps.get_model("chat_api", "Course")
    CourseTopic = apps.get_model("chat_api", "CourseTopic")

    for course in Course.objects.all():
        raw_expectations = getattr(course, "expectations", []) or []
        if not isinstance(raw_expectations, list):
            continue

        seen = set()
        for raw_expectation in raw_expectations:
            if not isinstance(raw_expectation, str):
                continue
            cleaned = " ".join(raw_expectation.strip().split())
            cleaned = _EXPECTATION_PREFIX_RE.sub("", cleaned).strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            CourseTopic.objects.get_or_create(course=course, name=cleaned)


class Migration(migrations.Migration):
    dependencies = [
        ("chat_api", "0006_seed_elementary_math_expectations"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="CourseTopic",
            new_name="Course",
        ),
        migrations.CreateModel(
            name="CourseTopic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("import_key", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="topics", to="chat_api.course"),
                ),
            ],
            options={
                "ordering": ("course_id", "name", "id"),
            },
        ),
        migrations.CreateModel(
            name="QuestionType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("hint_prompt", models.TextField()),
                ("mark_prompt", models.TextField()),
                ("import_key", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="question_types", to="chat_api.course"),
                ),
            ],
            options={
                "ordering": ("course_id", "name", "id"),
            },
        ),
        migrations.CreateModel(
            name="CourseQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question_text", models.TextField()),
                ("max_marks", models.PositiveIntegerField()),
                ("sample_answer", models.TextField(blank=True, default="")),
                ("marking_notes", models.TextField(blank=True, default="")),
                ("import_key", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="questions", to="chat_api.course"),
                ),
                (
                    "question_type",
                    models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="questions", to="chat_api.questiontype"),
                ),
                (
                    "topic",
                    models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="questions", to="chat_api.coursetopic"),
                ),
            ],
            options={
                "ordering": ("course_id", "topic_id", "id"),
            },
        ),
        migrations.RunPython(migrate_expectations_to_topics, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="course",
            name="answerer_prompt",
        ),
        migrations.RemoveField(
            model_name="course",
            name="briefer_prompt",
        ),
        migrations.RemoveField(
            model_name="course",
            name="categorizer_prompt",
        ),
        migrations.RemoveField(
            model_name="course",
            name="expectations",
        ),
        migrations.RemoveField(
            model_name="course",
            name="judge_prompt",
        ),
        migrations.RemoveField(
            model_name="course",
            name="planner_prompt",
        ),
        migrations.RemoveField(
            model_name="course",
            name="teacher_prompt",
        ),
        migrations.AddConstraint(
            model_name="coursetopic",
            constraint=models.UniqueConstraint(fields=("course", "name"), name="chat_api_course_topic_unique_name"),
        ),
        migrations.AddConstraint(
            model_name="questiontype",
            constraint=models.UniqueConstraint(fields=("course", "name"), name="chat_api_question_type_unique_name"),
        ),
    ]
