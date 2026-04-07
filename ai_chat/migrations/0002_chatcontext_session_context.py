from django.db import migrations, models
import django.db.models.deletion


def migrate_chat_contexts(apps, schema_editor):
    ChatContext = apps.get_model("ai_chat", "ChatContext")
    ChatSession = apps.get_model("ai_chat", "ChatSession")

    for context in ChatContext.objects.select_related("current_session", "compacted_through_turn").all():
        session = context.current_session
        if session is None:
            session = ChatSession.objects.filter(user_id=context.user_id).order_by("-created_at", "-id").first()

        if session is None:
            context.delete()
            continue

        context.session_id = session.id
        if context.compacted_through_turn_id is not None and context.compacted_through_turn.session_id != session.id:
            context.compacted_through_turn_id = None
        context.save(update_fields=["session", "compacted_through_turn"])


class Migration(migrations.Migration):
    dependencies = [
        ("ai_chat", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatcontext",
            name="session",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="context",
                to="ai_chat.chatsession",
            ),
        ),
        migrations.RunPython(migrate_chat_contexts, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="chatcontext",
            name="current_session",
        ),
        migrations.RemoveField(
            model_name="chatcontext",
            name="user_id",
        ),
        migrations.AlterModelOptions(
            name="chatcontext",
            options={"ordering": ("session_id",)},
        ),
        migrations.AlterField(
            model_name="chatcontext",
            name="session",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="context",
                to="ai_chat.chatsession",
            ),
        ),
    ]
