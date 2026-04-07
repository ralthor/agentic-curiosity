from __future__ import annotations

from django.conf import settings

from ai_chat import Chat, ChatPrompt, OpenAIAgent

DEFAULT_CATEGORIZER_MODEL = "gpt-5-mini"
DEFAULT_ANSWERER_MODEL = "gpt-5.4-mini"
DEFAULT_BRIEFER_MODEL = "gpt-5-mini"

TEACHER_PROMPT = (
    "You are a patient elementary math teacher. "
    "Teach one small arithmetic idea at a time in simple language. "
    "If the user has not asked a specific question, introduce a suitable elementary math topic and include "
    "a short check-for-understanding question. "
    "If the user asks a math question, answer it step by step and then ask a short follow-up question to verify understanding."
)

JUDGE_PROMPT = (
    "You are checking a student's elementary math answer. "
    "Decide whether the user's answer is correct. "
    "If it is correct, confirm it briefly and explain why. "
    "If it is incorrect, explain what went wrong in simple terms and show the correct reasoning. "
    "Always end by asking whether the user understood."
)

CATEGORIZER_SYSTEM = (
    "Choose the best prompt number for the next elementary math tutoring reply. "
    "Use the judging prompt when the student is attempting an answer. "
    "Use the teaching prompt when the student needs instruction, explanation, or a fresh exercise. "
    "Return only the number."
)

ANSWERER_SYSTEM = (
    "You are an elementary math tutor. "
    "Follow the selected prompt exactly. "
    "Keep the response concise, clear, and age-appropriate."
)

BRIEFER_SYSTEM = (
    "Condense the elementary math tutoring session. "
    "Keep the concepts covered, mistakes the student made, what they understood, and what still needs practice."
)


def _setting_value(name: str) -> str | None:
    value = getattr(settings, name, None)
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _resolve_agent_model(setting_name: str, *, default_model: str) -> str:
    return _setting_value(setting_name) or _setting_value("AI_CHAT_MODEL") or default_model


def create_session(*, user):
    return Chat.create_session(user_id=user.pk)


def build_chat(*, user, session_id: int | None = None) -> Chat:
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
    briefer_model = _resolve_agent_model(
        "AI_CHAT_BRIEFER_MODEL",
        default_model=DEFAULT_BRIEFER_MODEL,
    )

    return Chat(
        user_id=user.pk,
        session_id=session_id,
        prompts=[
            ChatPrompt("teacher", TEACHER_PROMPT),
            ChatPrompt("judge", JUDGE_PROMPT),
        ],
        categorizer_agent=OpenAIAgent(
            system=CATEGORIZER_SYSTEM,
            request_defaults={
                "model": categorizer_model,
            },
        ),
        answerer_agent=OpenAIAgent(
            system=ANSWERER_SYSTEM,
            request_defaults={
                "model": answerer_model,
            },
        ),
        briefer_agent=OpenAIAgent(
            system=BRIEFER_SYSTEM,
            request_defaults={
                "model": briefer_model,
            },
        ),
        context_threshold_bytes=threshold_bytes,
        recent_turns_to_keep=recent_turns,
    )
