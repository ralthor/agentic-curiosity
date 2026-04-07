from django.db import migrations


def backfill_session_course_topic(apps, schema_editor):
    ChatSession = apps.get_model("ai_chat", "ChatSession")
    CourseTopic = apps.get_model("chat_api", "CourseTopic")

    elementary_math = CourseTopic.objects.filter(name="Elementary Math").first()
    if elementary_math is None:
        return

    ChatSession.objects.filter(course_topic__isnull=True).update(course_topic=elementary_math)


class Migration(migrations.Migration):
    dependencies = [
        ("ai_chat", "0003_chatsession_course_topic"),
        ("chat_api", "0003_seed_elementary_math_topic"),
    ]

    operations = [
        migrations.RunPython(backfill_session_course_topic, migrations.RunPython.noop),
    ]
