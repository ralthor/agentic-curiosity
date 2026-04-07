from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .agents import Agent, ChatMessage
from .exceptions import AgentResponseError
from .models import ChatContext, ChatSession, ChatTurn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatPrompt:
    key: str
    text: str


PromptCollection = Mapping[str, str] | Sequence[ChatPrompt | tuple[str, str]]


class Chat:
    """Persisted multi-agent chat orchestration with prompt routing and context compaction."""

    def __init__(
        self,
        *,
        user_id: str | int,
        session_id: int | None = None,
        prompts: PromptCollection | None = None,
        categorizer_agent: Agent | None = None,
        answerer_agent: Agent | None = None,
        planner_agent: Agent | None = None,
        briefer_agent: Agent | None = None,
        context_threshold_bytes: int = 5_120,
        recent_turns_to_keep: int = 10,
        topic_name: str | None = None,
    ) -> None:
        if context_threshold_bytes <= 0:
            raise ValueError("context_threshold_bytes must be greater than zero.")
        if recent_turns_to_keep <= 0:
            raise ValueError("recent_turns_to_keep must be greater than zero.")

        self.user_id = str(user_id)
        self.session_id = session_id
        self.prompts = self._normalize_prompts(prompts or {})
        self.categorizer_agent = categorizer_agent
        self.answerer_agent = answerer_agent
        self.planner_agent = planner_agent
        self.briefer_agent = briefer_agent
        self.context_threshold_bytes = context_threshold_bytes
        self.recent_turns_to_keep = recent_turns_to_keep
        self.topic_name = topic_name.strip() if isinstance(topic_name, str) and topic_name.strip() else None

    @classmethod
    def create_session(cls, *, user_id: str | int) -> ChatSession:
        with transaction.atomic():
            session = ChatSession.objects.create(user_id=str(user_id))
            ChatContext.objects.create(session=session)
        logger.info("Created chat session %s for user %s.", session.pk, user_id)
        return session

    def reply(self, text: str, *, start_session: bool = False) -> str:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("text must not be blank.")
        if self.categorizer_agent is None:
            raise ValueError("categorizer_agent is required to send a reply.")
        if self.answerer_agent is None and self.planner_agent is None:
            raise ValueError("At least one response agent is required to send a reply.")
        if not self.prompts:
            raise ValueError("At least one prompt is required to send a reply.")

        logger.info(
            "Processing chat reply for user %s session %s start_session=%s text_length=%s.",
            self.user_id,
            self.session_id,
            start_session,
            len(cleaned_text),
        )
        session = self._ensure_session(start_session=start_session)
        context = self._ensure_context(session)
        turns = self._get_context_turns(context)
        logger.debug(
            "Loaded chat context for user %s session %s with %s turn(s) and summary_length=%s.",
            self.user_id,
            session.pk,
            len(turns),
            len(context.summary),
        )
        prompt_key = self._categorize_prompt_key(cleaned_text, context, turns)
        response = self._generate_response(
            prompt_key=prompt_key,
            user_text=cleaned_text,
            context=context,
            turns=turns,
        )

        with transaction.atomic():
            session = ChatSession.objects.select_for_update().get(pk=session.pk, user_id=self.user_id)
            turn = ChatTurn.objects.create(
                session=session,
                prompt_key=prompt_key,
                user_text=cleaned_text,
                agent_response=response,
            )
            now = timezone.now()
            ChatSession.objects.filter(pk=session.pk).update(updated_at=now)
            ChatContext.objects.filter(session=session).update(updated_at=now)
        logger.info(
            "Stored chat turn %s for user %s session %s prompt=%s response_length=%s.",
            turn.pk,
            self.user_id,
            session.pk,
            prompt_key,
            len(response),
        )

        if self.briefer_agent is not None:
            try:
                self.compact_context(force=False)
            except Exception:
                logger.exception("Automatic context compaction failed for session %s.", self.session_id)

        return response

    def compact_context(self, *, force: bool = False) -> bool:
        if self.briefer_agent is None:
            raise ValueError("briefer_agent is required to compact context.")
        if self.session_id is None:
            logger.debug("Skipping chat context compaction for user %s because no session is selected.", self.user_id)
            return False

        context = (
            ChatContext.objects.select_related("session", "compacted_through_turn")
            .filter(session_id=self.session_id, session__user_id=self.user_id)
            .first()
        )
        if context is None:
            logger.warning(
                "Skipping chat context compaction because session %s does not exist for user %s.",
                self.session_id,
                self.user_id,
            )
            return False

        return self._manage_context(context, force=force)

    @classmethod
    def compact_oversized_contexts(
        cls,
        *,
        briefer_agent: Agent,
        context_threshold_bytes: int = 5_120,
        recent_turns_to_keep: int = 10,
    ) -> int:
        compacted_count = 0
        contexts = ChatContext.objects.select_related("session__course_topic").order_by("session__user_id", "session_id")
        logger.info("Scanning %s stored chat context(s) for compaction.", contexts.count())

        for context in contexts:
            course_topic = context.session.course_topic
            chat = cls(
                user_id=context.session.user_id,
                session_id=context.session_id,
                prompts={"planner": course_topic.planner_prompt} if course_topic is not None else {},
                briefer_agent=briefer_agent,
                context_threshold_bytes=context_threshold_bytes,
                recent_turns_to_keep=recent_turns_to_keep,
                topic_name=course_topic.name if course_topic is not None else None,
            )
            if chat._manage_context(context, force=False):
                compacted_count += 1

        logger.info("Compacted %s stored chat context(s) in batch mode.", compacted_count)
        return compacted_count

    def _ensure_session(self, *, start_session: bool) -> ChatSession:
        with transaction.atomic():
            if start_session or self.session_id is None:
                session = self.create_session(user_id=self.user_id)
                self.session_id = session.pk
                logger.info(
                    "Started new chat session %s for user %s start_session=%s.",
                    session.pk,
                    self.user_id,
                    start_session,
                )
                return session

            session = ChatSession.objects.select_for_update().get(pk=self.session_id, user_id=self.user_id)
            logger.debug("Using existing chat session %s for user %s.", session.pk, self.user_id)
            return session

    def _ensure_context(self, session: ChatSession) -> ChatContext:
        context, _ = ChatContext.objects.get_or_create(session=session)
        logger.debug("Ensured chat context for user %s session %s.", self.user_id, session.pk)
        return context

    def _get_context_turns(self, context: ChatContext) -> list[ChatTurn]:
        turns = ChatTurn.objects.filter(session=context.session).select_related("session")
        if context.compacted_through_turn_id is not None:
            turns = turns.filter(id__gt=context.compacted_through_turn_id)
        return list(turns.order_by("created_at", "id"))

    def _categorize_prompt_key(self, user_text: str, context: ChatContext, turns: Sequence[ChatTurn]) -> str:
        prompt_options = "\n".join(
            f"{index}. {self._describe_prompt_for_categorizer(prompt_text)}"
            for index, prompt_text in enumerate(self.prompts.values(), start=1)
        )
        context_text = self._render_context_for_text(context, turns)
        sections = [
            "Choose the single best prompt for the next reply.\nReturn only the prompt number and nothing else."
        ]
        routing_guidance = self._build_routing_guidance()
        if routing_guidance:
            sections.append(f"Routing guidance:\n{routing_guidance}")
        if self.topic_name:
            sections.append(f"Current course topic:\n{self.topic_name}")
        sections.extend(
            [
                f"Available prompts:\n{prompt_options}",
                f"Current context:\n{context_text}",
                f"Latest user message:\n{user_text}",
            ]
        )
        categorizer_prompt = "\n\n".join(sections)
        raw_selection = self.categorizer_agent.ask(categorizer_prompt, user=self.user_id)
        prompt_key = self._parse_prompt_key(raw_selection)
        logger.info(
            "Selected prompt %s for user %s session %s from categorizer output %r.",
            prompt_key,
            self.user_id,
            context.session_id,
            raw_selection,
        )
        return prompt_key

    def _generate_response(
        self,
        *,
        prompt_key: str,
        user_text: str,
        context: ChatContext,
        turns: Sequence[ChatTurn],
    ) -> str:
        if prompt_key == "planner":
            if self.planner_agent is None:
                raise ValueError("planner_agent is required when the planner prompt is selected.")
            messages = self._build_agent_messages(
                self.planner_agent,
                *self._build_course_workflow_messages(prompt_key),
                *self._build_context_messages(context, turns),
                {"role": "user", "content": user_text},
            )
            return self.planner_agent.ask(messages=messages, user=self.user_id)

        if self.answerer_agent is None:
            raise ValueError("answerer_agent is required when a non-planner prompt is selected.")

        messages = self._build_agent_messages(
            self.answerer_agent,
            *self._build_course_workflow_messages(prompt_key),
            {"role": "system", "content": f"Selected prompt ({prompt_key}):\n{self.prompts[prompt_key]}"},
            *self._build_context_messages(context, turns),
            {"role": "user", "content": user_text},
        )
        return self.answerer_agent.ask(messages=messages, user=self.user_id)

    def _manage_context(self, context: ChatContext, *, force: bool) -> bool:
        turns = self._get_context_turns(context)
        current_size = self._context_size_bytes(context, turns)
        if not force and current_size <= self.context_threshold_bytes:
            logger.debug(
                "Skipping compaction for user %s session %s current_size=%s threshold=%s.",
                self.user_id,
                context.session_id,
                current_size,
                self.context_threshold_bytes,
            )
            return False

        turns_to_brief = list(turns[:-self.recent_turns_to_keep]) if len(turns) > self.recent_turns_to_keep else []
        if not context.summary.strip() and not turns_to_brief:
            logger.debug(
                "Skipping compaction for user %s session %s because there is nothing to condense.",
                self.user_id,
                context.session_id,
            )
            return False

        logger.info(
            "Compacting chat context for user %s session %s force=%s current_size=%s total_turns=%s turns_to_brief=%s.",
            self.user_id,
            context.session_id,
            force,
            current_size,
            len(turns),
            len(turns_to_brief),
        )
        briefing_sections = [
            "Condense the stored conversation context for future replies.\n"
            "Keep important user facts, preferences, constraints, decisions, open threads, and unresolved tasks.",
        ]
        if self.topic_name:
            briefing_sections.append(f"Current course topic:\n{self.topic_name}")
        if self._has_course_planner():
            briefing_sections.append(
                "Course planning state to preserve:\n"
                "- Do not lose the topic item list or progression.\n"
                "- Preserve which items are covered, fully understood, partially understood, or still remaining.\n"
                "- Keep any estimate of overall topic coverage and the next best item to teach."
            )
        briefing_sections.extend(
            [
                "Value recent details more than old details.\nReturn only the condensed context text.",
                f"Existing summary:\n{context.summary or '(none)'}",
                f"Turns to condense:\n{self._render_turns_for_briefing(turns_to_brief)}",
            ]
        )
        briefer_prompt = "\n\n".join(briefing_sections)
        condensed_context = self.briefer_agent.ask(briefer_prompt, user=self.user_id).strip()
        if not condensed_context:
            raise AgentResponseError("The briefer agent returned an empty condensed context.")

        compacted_through_turn = turns_to_brief[-1] if turns_to_brief else context.compacted_through_turn
        ChatContext.objects.filter(pk=context.pk).update(
            summary=condensed_context,
            compacted_through_turn=compacted_through_turn,
            last_compacted_at=timezone.now(),
            updated_at=timezone.now(),
        )
        logger.info(
            "Compacted chat context for user %s session %s summary_length=%s compacted_through_turn_id=%s.",
            self.user_id,
            context.session_id,
            len(condensed_context),
            getattr(compacted_through_turn, "id", None),
        )
        return True

    def _build_context_messages(
        self,
        context: ChatContext,
        turns: Sequence[ChatTurn],
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        if context.summary.strip():
            messages.append(
                {
                    "role": "system",
                    "content": f"Summary of older conversation context:\n{context.summary.strip()}",
                }
            )

        for turn in turns:
            messages.append({"role": "user", "content": turn.user_text})
            messages.append({"role": "assistant", "content": turn.agent_response})

        return messages

    def _build_agent_messages(self, agent: Agent, *messages: ChatMessage) -> list[ChatMessage]:
        built_messages: list[ChatMessage] = []
        if agent.system:
            built_messages.append({"role": "system", "content": agent.system})
        built_messages.extend(messages)
        return built_messages

    def _build_routing_guidance(self) -> str:
        guidance: list[str] = []
        if "planner" in self.prompts:
            guidance.append(
                "- Use the planner prompt when the student asks what comes next, when they clearly mastered the current item, or when you need covered-versus-remaining topic progress."
            )
        if "judge" in self.prompts:
            guidance.append("- Use the judge prompt when the student is attempting an answer that should be checked.")
        if "teacher" in self.prompts:
            guidance.append("- Use the teacher prompt when the student needs explanation, teaching, or more practice on the current item.")
        return "\n".join(guidance)

    def _build_course_workflow_messages(self, prompt_key: str) -> list[ChatMessage]:
        if not self.topic_name and not self._has_course_planner():
            return []

        lines: list[str] = []
        if self.topic_name:
            lines.append(f"Current course topic: {self.topic_name}.")
        if self._has_course_planner():
            lines.extend(
                [
                    "Keep the conversation inside the current topic.",
                    "Preserve which topic items are covered, mastered, in progress, and remaining.",
                    "Use the planner route for choosing the next teaching item and reporting overall topic coverage.",
                ]
            )
            if prompt_key == "teacher":
                lines.append("Teach the current item without silently replacing the course plan.")
            elif prompt_key == "judge":
                lines.append("If the student has clearly mastered the current item, say so plainly so the next step can use the planner.")
            elif prompt_key == "planner":
                lines.append(
                    "Act as the course planner: infer or maintain an ordered topic-item list, estimate how much is covered, identify what remains, and recommend the next teaching item."
                )

        return [{"role": "system", "content": "\n".join(lines)}]

    def _has_course_planner(self) -> bool:
        return "planner" in self.prompts or self.planner_agent is not None

    def _render_context_for_text(self, context: ChatContext, turns: Sequence[ChatTurn]) -> str:
        if not context.summary.strip() and not turns:
            return "(empty)"

        lines: list[str] = []
        if context.summary.strip():
            lines.append(f"Summary:\n{context.summary.strip()}")

        lines.append(self._render_turns_for_briefing(turns))
        return "\n\n".join(line for line in lines if line.strip())

    def _render_turns_for_briefing(self, turns: Sequence[ChatTurn]) -> str:
        if not turns:
            return "(none)"

        parts: list[str] = []
        for turn in turns:
            parts.append(
                "\n".join(
                    [
                        f"Prompt key: {turn.prompt_key}",
                        f"User: {turn.user_text}",
                        f"Assistant: {turn.agent_response}",
                    ]
                )
            )

        return "\n\n".join(parts)

    def _context_size_bytes(self, context: ChatContext, turns: Sequence[ChatTurn]) -> int:
        size = len(context.summary.encode("utf-8"))
        for turn in turns:
            size += len(turn.prompt_key.encode("utf-8"))
            size += len(turn.user_text.encode("utf-8"))
            size += len(turn.agent_response.encode("utf-8"))
        return size

    def _normalize_prompts(self, prompts: PromptCollection) -> dict[str, str]:
        normalized: dict[str, str] = {}
        items: Sequence[tuple[str, str]]

        if isinstance(prompts, Mapping):
            items = [(str(key), str(value)) for key, value in prompts.items()]
        else:
            converted_items: list[tuple[str, str]] = []
            for item in prompts:
                if isinstance(item, ChatPrompt):
                    converted_items.append((item.key, item.text))
                else:
                    key, value = item
                    converted_items.append((str(key), str(value)))
            items = converted_items

        for key, value in items:
            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("Prompt keys must not be blank.")
            if normalized_key in normalized:
                raise ValueError(f"Duplicate prompt key: {normalized_key}")
            normalized[normalized_key] = value

        return normalized

    def _describe_prompt_for_categorizer(self, prompt_text: str) -> str:
        normalized_text = " ".join(line.strip() for line in prompt_text.splitlines() if line.strip())
        if not normalized_text:
            return "(blank prompt)"
        if len(normalized_text) <= 120:
            return normalized_text

        truncated = normalized_text[:117].rstrip()
        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        return f"{truncated}..."

    def _parse_prompt_key(self, raw_selection: str) -> str:
        stripped = raw_selection.strip().strip("`").strip()
        prompt_keys = list(self.prompts)

        numeric_match = re.search(r"\b(\d+)\b", stripped)
        if numeric_match:
            prompt_index = int(numeric_match.group(1)) - 1
            if 0 <= prompt_index < len(prompt_keys):
                return prompt_keys[prompt_index]

        if stripped in self.prompts:
            return stripped

        lower_key_map = {key.lower(): key for key in self.prompts}
        lowered = stripped.lower()
        if lowered in lower_key_map:
            return lower_key_map[lowered]

        for line in stripped.splitlines():
            candidate = line.strip().strip("`").strip("*- ").strip()
            if candidate in self.prompts:
                return candidate

            lowered_candidate = candidate.lower()
            if lowered_candidate in lower_key_map:
                return lower_key_map[lowered_candidate]

        for key in self.prompts:
            if re.search(rf"\b{re.escape(key)}\b", raw_selection, flags=re.IGNORECASE):
                return key

        raise AgentResponseError(f"The categorizer agent returned an unknown prompt key: {raw_selection!r}")
