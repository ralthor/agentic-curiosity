from django.db import migrations


def _build_initial_course_state(expectations):
    cleaned_expectations = [item.strip() for item in expectations if isinstance(item, str) and item.strip()]
    first_item = cleaned_expectations[0] if cleaned_expectations else None
    return {
        "expectations": [
            {
                "expectation": expectation,
                "score": 0,
                "status": "not_started",
                "evidence": "",
            }
            for expectation in cleaned_expectations
        ],
        "overall_progress": 0,
        "current_item": first_item,
        "next_item": first_item,
        "summary": "No assessed evidence yet." if cleaned_expectations else "",
        "reply_focus": "Start with the first unmet expectation." if first_item else "",
    }


def backfill_chat_session_course_state(apps, schema_editor):
    ChatSession = apps.get_model("ai_chat", "ChatSession")

    for session in ChatSession.objects.select_related("course_topic").all():
        if session.course_state:
            continue

        course_topic = session.course_topic
        expectations = course_topic.expectations if course_topic is not None else []
        if not expectations:
            continue

        session.course_state = _build_initial_course_state(expectations)
        session.save(update_fields=["course_state"])


class Migration(migrations.Migration):
    dependencies = [
        ("ai_chat", "0006_chatsession_course_state"),
        ("chat_api", "0006_seed_elementary_math_expectations"),
    ]

    operations = [
        migrations.RunPython(backfill_chat_session_course_state, migrations.RunPython.noop),
    ]
