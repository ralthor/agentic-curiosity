from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string

from ai_chat import Agent, Chat


class Command(BaseCommand):
    help = "Compact oversized stored chat contexts with a configured briefer agent."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--agent-class",
            required=True,
            help="Dotted import path to an Agent subclass used for briefing.",
        )
        parser.add_argument(
            "--model",
            required=True,
            help="Model name passed to the briefing agent.",
        )
        parser.add_argument(
            "--system",
            default=None,
            help="Optional system prompt override for the briefing agent.",
        )
        parser.add_argument(
            "--threshold-bytes",
            type=int,
            default=5_120,
            help="Context size threshold before compaction runs.",
        )
        parser.add_argument(
            "--recent-turns",
            type=int,
            default=10,
            help="Number of recent turns to keep outside the condensed summary.",
        )

    def handle(self, *args, **options) -> None:
        agent_class_path = options["agent_class"]
        threshold_bytes = options["threshold_bytes"]
        recent_turns = options["recent_turns"]

        try:
            agent_class = import_string(agent_class_path)
        except ImportError as exc:
            raise CommandError(f"Could not import agent class {agent_class_path!r}: {exc}") from exc

        if not isinstance(agent_class, type) or not issubclass(agent_class, Agent):
            raise CommandError(f"{agent_class_path!r} is not an Agent subclass.")
        if threshold_bytes <= 0:
            raise CommandError("--threshold-bytes must be greater than zero.")
        if recent_turns <= 0:
            raise CommandError("--recent-turns must be greater than zero.")

        briefer_agent = agent_class(model=options["model"], system=options["system"])
        compacted_count = Chat.compact_oversized_contexts(
            briefer_agent=briefer_agent,
            context_threshold_bytes=threshold_bytes,
            recent_turns_to_keep=recent_turns,
        )
        self.stdout.write(self.style.SUCCESS(f"Compacted {compacted_count} chat context(s)."))
