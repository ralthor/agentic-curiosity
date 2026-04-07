from __future__ import annotations

from django.conf import settings

from ai_chat import Chat, ChatPrompt, OpenAIAgent

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


def create_session(*, user):
    return Chat.create_session(user_id=user.pk)


def build_chat(*, user, session_id: int | None = None) -> Chat:
    model_name = getattr(settings, "AI_CHAT_MODEL", "gpt-4.1-mini")
    threshold_bytes = getattr(settings, "AI_CHAT_CONTEXT_THRESHOLD_BYTES", 5_120)
    recent_turns = getattr(settings, "AI_CHAT_RECENT_TURNS_TO_KEEP", 10)

    return Chat(
        user_id=user.pk,
        session_id=session_id,
        prompts=[
            ChatPrompt("teacher", TEACHER_PROMPT),
            ChatPrompt("judge", JUDGE_PROMPT),
        ],
        categorizer_agent=OpenAIAgent(
            model=model_name,
            system=CATEGORIZER_SYSTEM,
            temperature=0,
        ),
        answerer_agent=OpenAIAgent(
            model=model_name,
            system=ANSWERER_SYSTEM,
            temperature=0.4,
        ),
        briefer_agent=OpenAIAgent(
            model=model_name,
            system=BRIEFER_SYSTEM,
            temperature=0.2,
        ),
        context_threshold_bytes=threshold_bytes,
        recent_turns_to_keep=recent_turns,
    )
