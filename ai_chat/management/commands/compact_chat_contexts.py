from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Deprecated. The question-first engine no longer uses global chat context compaction."

    def handle(self, *args, **options) -> None:
        raise CommandError("compact_chat_contexts is not supported in the question-first engine.")
