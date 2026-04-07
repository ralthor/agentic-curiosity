from django.db import migrations, models


def backfill_chat_timestamps(apps, schema_editor):
    ChatContext = apps.get_model("ai_chat", "ChatContext")
    ChatTurn = apps.get_model("ai_chat", "ChatTurn")

    contexts_to_update = []
    for context in ChatContext.objects.select_related("session").all():
        if context.created_at is None:
            context.created_at = context.session.created_at or context.updated_at
            contexts_to_update.append(context)
    if contexts_to_update:
        ChatContext.objects.bulk_update(contexts_to_update, ["created_at"])

    turns_to_update = []
    for turn in ChatTurn.objects.all():
        if turn.updated_at is None:
            turn.updated_at = turn.created_at
            turns_to_update.append(turn)
    if turns_to_update:
        ChatTurn.objects.bulk_update(turns_to_update, ["updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("ai_chat", "0004_backfill_session_course_topic"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatcontext",
            name="created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chatturn",
            name="updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_chat_timestamps, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="chatcontext",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="chatturn",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
