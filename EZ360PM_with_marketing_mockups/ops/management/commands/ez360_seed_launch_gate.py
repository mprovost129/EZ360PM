from __future__ import annotations

from django.core.management.base import BaseCommand

from ops.launch_gate_defaults import DEFAULT_LAUNCH_GATE_ITEMS
from ops.models import LaunchGateItem


class Command(BaseCommand):
    help = "Seed default Launch Gate checklist items (non-destructive)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Create missing items even if some items already exist.",
        )

    def handle(self, *args, **options):
        force = bool(options.get("force"))

        existing_keys = set(LaunchGateItem.objects.values_list("key", flat=True))
        created = 0
        skipped = 0

        if existing_keys and not force:
            self.stdout.write(self.style.WARNING("Launch Gate already has items; use --force to add missing defaults."))

        for item in DEFAULT_LAUNCH_GATE_ITEMS:
            key = item["key"]
            if key in existing_keys and not force:
                skipped += 1
                continue

            obj, was_created = LaunchGateItem.objects.get_or_create(
                key=key,
                defaults={
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                },
            )
            if was_created:
                created += 1
            else:
                # If forcing, fill blank fields only (do not overwrite staff edits).
                if force:
                    changed = False
                    if not obj.title and item.get("title"):
                        obj.title = item["title"]
                        changed = True
                    if not obj.description and item.get("description"):
                        obj.description = item["description"]
                        changed = True
                    if changed:
                        obj.save(update_fields=["title", "description"])

        self.stdout.write(self.style.SUCCESS(f"Launch Gate seed complete. Created: {created}. Skipped: {skipped}."))
