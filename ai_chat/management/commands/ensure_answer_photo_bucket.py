from __future__ import annotations

from django.core.management.base import BaseCommand

from ai_chat.storage import get_object_storage, object_storage_is_configured


class Command(BaseCommand):
    help = "Ensure the configured answer photo object-storage bucket exists."

    def handle(self, *args, **options):
        if not object_storage_is_configured():
            self.stdout.write(self.style.WARNING("Answer photo storage is not configured; skipping bucket check."))
            return

        storage = get_object_storage()
        created = storage.ensure_bucket()
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created answer photo bucket {storage.bucket!r}."))
            return

        self.stdout.write(self.style.SUCCESS(f"Answer photo bucket {storage.bucket!r} is ready."))
