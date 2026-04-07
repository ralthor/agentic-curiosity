from __future__ import annotations

from django.conf import settings
from django.db import transaction

from ai_chat import Chat, ChatPrompt, OpenAIAgent
from ai_chat.models import ChatContext, ChatSession

from .models import CourseTopic

DEFAULT_CATEGORIZER_MODEL = "gpt-5-mini"
DEFAULT_ANSWERER_MODEL = "gpt-5.4-mini"
DEFAULT_PLANNER_MODEL = "gpt-5-mini"
DEFAULT_BRIEFER_MODEL = "gpt-5-mini"


def _setting_value(name: str) -> str | None:
    value = getattr(settings, name, None)
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _resolve_agent_model(setting_name: str, *, default_model: str) -> str:
    return _setting_value(setting_name) or _setting_value("AI_CHAT_MODEL") or default_model


def get_session(*, user, session_id: int) -> ChatSession:
    return ChatSession.objects.select_related("course_topic").get(
        pk=session_id,
        user_id=str(user.pk),
    )


def create_session(*, user, course_topic: CourseTopic) -> ChatSession:
    with transaction.atomic():
        session = ChatSession.objects.create(
            user_id=str(user.pk),
            course_topic=course_topic,
        )
        ChatContext.objects.create(session=session)
    return session


def _resolve_course_topic(
    *,
    user,
    session_id: int | None = None,
    course_topic: CourseTopic | None = None,
) -> CourseTopic:
    if course_topic is not None:
        return course_topic

    if session_id is None:
        raise ValueError("session_id is required to load the course topic.")

    session = get_session(user=user, session_id=session_id)
    if session.course_topic is None:
        raise ValueError("Session does not have a course topic.")

    return session.course_topic


def build_chat(
    *,
    user,
    session_id: int | None = None,
    course_topic: CourseTopic | None = None,
) -> Chat:
    threshold_bytes = getattr(settings, "AI_CHAT_CONTEXT_THRESHOLD_BYTES", 5_120)
    recent_turns = getattr(settings, "AI_CHAT_RECENT_TURNS_TO_KEEP", 10)
    categorizer_model = _resolve_agent_model(
        "AI_CHAT_CATEGORIZER_MODEL",
        default_model=DEFAULT_CATEGORIZER_MODEL,
    )
    answerer_model = _resolve_agent_model(
        "AI_CHAT_ANSWERER_MODEL",
        default_model=DEFAULT_ANSWERER_MODEL,
    )
    planner_model = _resolve_agent_model(
        "AI_CHAT_PLANNER_MODEL",
        default_model=DEFAULT_PLANNER_MODEL,
    )
    briefer_model = _resolve_agent_model(
        "AI_CHAT_BRIEFER_MODEL",
        default_model=DEFAULT_BRIEFER_MODEL,
    )
    resolved_course_topic = _resolve_course_topic(
        user=user,
        session_id=session_id,
        course_topic=course_topic,
    )

    return Chat(
        user_id=user.pk,
        session_id=session_id,
        topic_name=resolved_course_topic.name,
        prompts=[
            ChatPrompt("teacher", resolved_course_topic.teacher_prompt),
            ChatPrompt("judge", resolved_course_topic.judge_prompt),
        ],
        categorizer_agent=OpenAIAgent(
            system=resolved_course_topic.categorizer_prompt,
            request_defaults={
                "model": categorizer_model,
            },
        ),
        answerer_agent=OpenAIAgent(
            system=resolved_course_topic.answerer_prompt,
            request_defaults={
                "model": answerer_model,
            },
        ),
        planner_agent=OpenAIAgent(
            system=resolved_course_topic.planner_prompt,
            request_defaults={
                "model": planner_model,
            },
        ),
        briefer_agent=OpenAIAgent(
            system=resolved_course_topic.briefer_prompt,
            request_defaults={
                "model": briefer_model,
            },
        ),
        context_threshold_bytes=threshold_bytes,
        recent_turns_to_keep=recent_turns,
        planner_prompt=resolved_course_topic.planner_prompt,
    )
