from django.db import migrations


def seed_elementary_math_topic(apps, schema_editor):
    CourseTopic = apps.get_model("chat_api", "CourseTopic")
    CourseTopic.objects.get_or_create(
        name="Elementary Math",
        defaults={
            "teacher_prompt": (
                "You are a patient elementary math teacher. "
                "Teach one small arithmetic idea at a time in simple language. "
                "If the user has not asked a specific question, introduce a suitable elementary math topic and include "
                "a short check-for-understanding question. "
                "If the user asks a math question, answer it step by step and then ask a short follow-up question to verify understanding."
            ),
            "judge_prompt": (
                "You are checking a student's elementary math answer. "
                "Decide whether the user's answer is correct. "
                "If it is correct, confirm it briefly and explain why. "
                "If it is incorrect, explain what went wrong in simple terms and show the correct reasoning. "
                "Always end by asking whether the user understood."
            ),
            "categorizer_prompt": (
                "Choose the best prompt number for the next elementary math tutoring reply. "
                "Use the judging prompt when the student is attempting an answer. "
                "Use the teaching prompt when the student needs instruction, explanation, or a fresh exercise. "
                "Return only the number."
            ),
            "answerer_prompt": (
                "You are an elementary math tutor. "
                "Follow the selected prompt exactly. "
                "Keep the response concise, clear, and age-appropriate."
            ),
            "briefer_prompt": (
                "Condense the elementary math tutoring session. "
                "Keep the concepts covered, mistakes the student made, what they understood, and what still needs practice."
            ),
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("chat_api", "0002_coursetopic"),
    ]

    operations = [
        migrations.RunPython(seed_elementary_math_topic, migrations.RunPython.noop),
    ]
