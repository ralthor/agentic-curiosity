from django.db import migrations, models


DEFAULT_PLANNER_PROMPT = (
    "You are the course planner for this topic. "
    "Infer or maintain a sensible ordered list of teaching items inside the current topic. "
    "Track which items are covered, fully understood, partially understood, and still remaining. "
    "Estimate overall progress through the topic and recommend the next best teaching item without leaving the topic."
)


class Migration(migrations.Migration):
    dependencies = [
        ("chat_api", "0003_seed_elementary_math_topic"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursetopic",
            name="planner_prompt",
            field=models.TextField(default=DEFAULT_PLANNER_PROMPT),
            preserve_default=False,
        ),
    ]
