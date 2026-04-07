from django.db import migrations


ELEMENTARY_MATH_EXPECTATIONS = [
    "Count forward and backward within 20.",
    "Add within 20 using objects, drawings, or equations.",
    "Subtract within 20 using objects, drawings, or equations.",
    "Recall addition and subtraction facts within 10 with fluency.",
    "Solve one-step word problems within 20 using addition or subtraction.",
    "Understand two-digit numbers as tens and ones.",
]


def seed_elementary_math_expectations(apps, schema_editor):
    CourseTopic = apps.get_model("chat_api", "CourseTopic")
    CourseTopic.objects.filter(name="Elementary Math").update(expectations=ELEMENTARY_MATH_EXPECTATIONS)


class Migration(migrations.Migration):
    dependencies = [
        ("chat_api", "0005_coursetopic_expectations"),
    ]

    operations = [
        migrations.RunPython(seed_elementary_math_expectations, migrations.RunPython.noop),
    ]
