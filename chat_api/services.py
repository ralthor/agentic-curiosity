from __future__ import annotations

import json
import re
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ai_chat import OpenAIAgent
from ai_chat.models import ChatSession, LearnerQuestionState, QuestionAttempt, QuestionPresentation

from .models import Course, CourseQuestion, CourseTopic
from .progress import derive_leitner_score, schedule_due_at
from .question_selector import select_next_question

DEFAULT_INTERACTION_MODEL = "gpt-5.4-mini"
_SKIP_RE = re.compile(r"\b(skip|next question|move on|pass|i want to skip|skip this)\b", re.IGNORECASE)
_HINT_RE = re.compile(
    r"^(hint|help|explain|show|what|how|why|can|could|i don't understand|i do not understand|give me a clue)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InteractionResult:
    interaction_type: str
    message: str
    awarded_marks: int | None
    derived_leitner_score: int | None
    completed_presentation: bool


def _setting_value(name: str) -> str | None:
    value = getattr(settings, name, None)
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _resolve_agent_model() -> str:
    return _setting_value("AI_CHAT_ANSWERER_MODEL") or _setting_value("AI_CHAT_MODEL") or DEFAULT_INTERACTION_MODEL


def _session_queryset():
    return ChatSession.objects.select_related(
        "course",
        "active_presentation__question__topic",
        "active_presentation__question__question_type",
        "selector_override_topic",
        "selector_override_question",
    )


def get_session(*, user, session_id: int) -> ChatSession:
    return _session_queryset().get(pk=session_id, user_id=str(user.pk))


def create_session(
    *,
    user,
    course: Course,
    selector_override_topic: CourseTopic | None = None,
    selector_override_question: CourseQuestion | None = None,
    selector_strategy_override: str = "",
) -> ChatSession:
    _validate_selector_overrides(
        course=course,
        selector_override_topic=selector_override_topic,
        selector_override_question=selector_override_question,
    )

    with transaction.atomic():
        session = ChatSession.objects.create(
            user_id=str(user.pk),
            course=course,
            selector_override_topic=selector_override_topic,
            selector_override_question=selector_override_question,
            selector_strategy_override=selector_strategy_override.strip(),
        )
        presentation = _assign_next_question(session=session)
        if presentation is None:
            raise ValueError("Course has no questions available.")
    return get_session(user=user, session_id=session.pk)


def interact_with_session(*, user, session_id: int, text: str) -> tuple[ChatSession, InteractionResult]:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("text must not be blank.")

    with transaction.atomic():
        session = _session_queryset().select_for_update().get(pk=session_id, user_id=str(user.pk))
        presentation = session.active_presentation
        if presentation is None:
            presentation = _assign_next_question(session=session)
            if presentation is None:
                raise ValueError("Course has no remaining questions available for this session.")
            session = _session_queryset().select_for_update().get(pk=session_id, user_id=str(user.pk))
            presentation = session.active_presentation

        interaction_type = classify_interaction(cleaned_text)
        if interaction_type == QuestionAttempt.InteractionType.HINT_REQUEST:
            result = _handle_hint_request(session=session, presentation=presentation, student_message=cleaned_text)
        elif interaction_type == QuestionAttempt.InteractionType.SKIP:
            result = _handle_skip(session=session, presentation=presentation, student_message=cleaned_text)
        else:
            result = _handle_answer_attempt(session=session, presentation=presentation, student_message=cleaned_text)

        ChatSession.objects.filter(pk=session.pk).update(updated_at=timezone.now())

    return get_session(user=user, session_id=session_id), result


def classify_interaction(text: str) -> str:
    stripped = text.strip()
    if _SKIP_RE.search(stripped):
        return QuestionAttempt.InteractionType.SKIP
    if "?" in stripped or _HINT_RE.search(stripped):
        return QuestionAttempt.InteractionType.HINT_REQUEST
    return QuestionAttempt.InteractionType.ANSWER_ATTEMPT


def _handle_hint_request(*, session: ChatSession, presentation: QuestionPresentation, student_message: str) -> InteractionResult:
    question = presentation.question
    prior_attempts = _recent_attempts(presentation)
    agent = OpenAIAgent(
        system=question.question_type.hint_prompt,
        request_defaults={"model": _resolve_agent_model()},
    )
    response_text = agent.ask(
        text=_build_hint_prompt(
            session=session,
            presentation=presentation,
            prior_attempts=prior_attempts,
            student_message=student_message,
        ),
        user=session.user_id,
    ).strip()
    QuestionAttempt.objects.create(
        presentation=presentation,
        interaction_type=QuestionAttempt.InteractionType.HINT_REQUEST,
        student_message=student_message,
        model_response_text=response_text,
        completed_presentation=False,
    )
    return InteractionResult(
        interaction_type=QuestionAttempt.InteractionType.HINT_REQUEST,
        message=response_text,
        awarded_marks=None,
        derived_leitner_score=None,
        completed_presentation=False,
    )


def _handle_answer_attempt(*, session: ChatSession, presentation: QuestionPresentation, student_message: str) -> InteractionResult:
    question = presentation.question
    prior_attempts = _recent_attempts(presentation)
    agent = OpenAIAgent(
        system=question.question_type.mark_prompt,
        request_defaults={"model": _resolve_agent_model()},
    )
    raw_response = agent.ask(
        text=_build_mark_prompt(
            session=session,
            presentation=presentation,
            prior_attempts=prior_attempts,
            student_message=student_message,
        ),
        user=session.user_id,
    ).strip()
    awarded_marks, explanation = _parse_mark_response(raw_response, max_marks=question.max_marks)
    derived_leitner_score = derive_leitner_score(awarded_marks=awarded_marks, max_marks=question.max_marks)
    completed_presentation = awarded_marks >= question.max_marks
    now = timezone.now()
    QuestionAttempt.objects.create(
        presentation=presentation,
        interaction_type=QuestionAttempt.InteractionType.ANSWER_ATTEMPT,
        student_message=student_message,
        model_response_text=explanation,
        awarded_marks=awarded_marks,
        derived_leitner_score=derived_leitner_score,
        completed_presentation=completed_presentation,
    )
    _update_learner_state_after_answer(
        session=session,
        question=question,
        leitner_score=derived_leitner_score,
        completed_presentation=completed_presentation,
        updated_at=now,
    )
    if completed_presentation:
        _close_presentation(
            presentation=presentation,
            status=QuestionPresentation.Status.COMPLETED,
            closed_at=now,
        )
        _assign_next_question(session=session, exclude_question_id=question.id)
    return InteractionResult(
        interaction_type=QuestionAttempt.InteractionType.ANSWER_ATTEMPT,
        message=explanation,
        awarded_marks=awarded_marks,
        derived_leitner_score=derived_leitner_score,
        completed_presentation=completed_presentation,
    )


def _handle_skip(*, session: ChatSession, presentation: QuestionPresentation, student_message: str) -> InteractionResult:
    now = timezone.now()
    QuestionAttempt.objects.create(
        presentation=presentation,
        interaction_type=QuestionAttempt.InteractionType.SKIP,
        student_message=student_message,
        model_response_text="Skipped. Moving to the next question.",
        completed_presentation=True,
    )
    _update_learner_state_after_skip(session=session, question=presentation.question, updated_at=now)
    _close_presentation(
        presentation=presentation,
        status=QuestionPresentation.Status.SKIPPED,
        closed_at=now,
    )
    _assign_next_question(session=session, exclude_question_id=presentation.question_id)
    return InteractionResult(
        interaction_type=QuestionAttempt.InteractionType.SKIP,
        message="Skipped. Moving to the next question.",
        awarded_marks=None,
        derived_leitner_score=None,
        completed_presentation=True,
    )


def _assign_next_question(*, session: ChatSession, exclude_question_id: int | None = None) -> QuestionPresentation | None:
    selection = select_next_question(
        user_id=session.user_id,
        course=session.course,
        session=session,
        exclude_question_id=exclude_question_id,
    )
    if selection is None:
        session.active_presentation = None
        session.save(update_fields=["active_presentation", "updated_at"])
        return None

    presented_at = timezone.now()
    presentation = QuestionPresentation.objects.create(
        session=session,
        question=selection.question,
        selection_source=selection.source,
    )
    _mark_question_presented(
        user_id=session.user_id,
        course=session.course,
        question=selection.question,
        presented_at=presented_at,
    )
    session.active_presentation = presentation
    session.save(update_fields=["active_presentation", "updated_at"])
    return presentation


def _mark_question_presented(*, user_id: str, course: Course, question: CourseQuestion, presented_at) -> None:
    state, created = LearnerQuestionState.objects.get_or_create(
        user_id=user_id,
        course=course,
        question=question,
        defaults={
            "due_at": presented_at,
            "times_seen": 1,
            "last_presented_at": presented_at,
        },
    )
    if created:
        return

    state.times_seen += 1
    state.last_presented_at = presented_at
    state.save(update_fields=["times_seen", "last_presented_at", "updated_at"])


def _update_learner_state_after_answer(
    *,
    session: ChatSession,
    question: CourseQuestion,
    leitner_score: int,
    completed_presentation: bool,
    updated_at,
) -> None:
    state, _ = LearnerQuestionState.objects.get_or_create(
        user_id=session.user_id,
        course=session.course,
        question=question,
        defaults={
            "due_at": updated_at,
            "last_presented_at": updated_at,
        },
    )
    state.latest_leitner_score = leitner_score
    state.best_leitner_score = max(state.best_leitner_score, leitner_score)
    state.times_answered += 1
    state.due_at = schedule_due_at(from_time=updated_at, leitner_score=leitner_score)
    if completed_presentation:
        state.last_completed_at = updated_at
    state.save(
        update_fields=[
            "latest_leitner_score",
            "best_leitner_score",
            "times_answered",
            "due_at",
            "last_completed_at",
            "updated_at",
        ],
    )


def _update_learner_state_after_skip(*, session: ChatSession, question: CourseQuestion, updated_at) -> None:
    state, _ = LearnerQuestionState.objects.get_or_create(
        user_id=session.user_id,
        course=session.course,
        question=question,
        defaults={
            "due_at": updated_at,
            "last_presented_at": updated_at,
        },
    )
    state.latest_leitner_score = 0
    state.due_at = updated_at
    state.last_completed_at = updated_at
    state.save(update_fields=["latest_leitner_score", "due_at", "last_completed_at", "updated_at"])


def _close_presentation(*, presentation: QuestionPresentation, status: str, closed_at) -> None:
    QuestionPresentation.objects.filter(pk=presentation.pk).update(
        status=status,
        closed_at=closed_at,
        updated_at=closed_at,
    )


def _recent_attempts(presentation: QuestionPresentation) -> list[QuestionAttempt]:
    attempts = list(
        presentation.attempts.order_by("-created_at", "-id")[:3]
    )
    attempts.reverse()
    return attempts


def _build_hint_prompt(
    *,
    session: ChatSession,
    presentation: QuestionPresentation,
    prior_attempts: list[QuestionAttempt],
    student_message: str,
) -> str:
    question = presentation.question
    sections = [
        f"Course: {session.course.name}",
        f"Topic: {question.topic.name}",
        f"Question type: {question.question_type.name}",
        f"Question:\n{question.question_text}",
        f"Maximum marks: {question.max_marks}",
    ]
    if question.sample_answer:
        sections.append(f"Sample answer:\n{question.sample_answer}")
    if question.marking_notes:
        sections.append(f"Marking notes:\n{question.marking_notes}")
    sections.append(f"Prior attempts on this question:\n{_render_attempts(prior_attempts)}")
    sections.append(f"Latest student message:\n{student_message}")
    sections.append(
        "Give a direct hint or explanation for this question only. "
        "Do not mark the answer, do not refer to any broader course history, and keep the response concise."
    )
    return "\n\n".join(sections)


def _build_mark_prompt(
    *,
    session: ChatSession,
    presentation: QuestionPresentation,
    prior_attempts: list[QuestionAttempt],
    student_message: str,
) -> str:
    question = presentation.question
    sections = [
        f"Course: {session.course.name}",
        f"Topic: {question.topic.name}",
        f"Question type: {question.question_type.name}",
        f"Question:\n{question.question_text}",
        f"Maximum marks: {question.max_marks}",
    ]
    if question.sample_answer:
        sections.append(f"Sample answer:\n{question.sample_answer}")
    if question.marking_notes:
        sections.append(f"Marking notes:\n{question.marking_notes}")
    sections.append(f"Prior attempts on this question:\n{_render_attempts(prior_attempts)}")
    sections.append(f"Latest student answer:\n{student_message}")
    sections.append('Return only valid JSON in the shape {"awarded_marks": 0, "explanation": "..."} .')
    return "\n\n".join(sections)


def _render_attempts(prior_attempts: list[QuestionAttempt]) -> str:
    if not prior_attempts:
        return "(none)"

    rendered: list[str] = []
    for attempt in prior_attempts:
        lines = [
            f"Interaction type: {attempt.interaction_type}",
            f"Student message: {attempt.student_message}",
        ]
        if attempt.model_response_text:
            lines.append(f"Model response: {attempt.model_response_text}")
        if attempt.awarded_marks is not None:
            lines.append(f"Awarded marks: {attempt.awarded_marks}")
        if attempt.derived_leitner_score is not None:
            lines.append(f"Derived Leitner score: {attempt.derived_leitner_score}")
        rendered.append("\n".join(lines))
    return "\n\n".join(rendered)


def _parse_mark_response(raw_response: str, *, max_marks: int) -> tuple[int, str]:
    try:
        parsed = json.loads(_strip_json_fence(raw_response))
    except json.JSONDecodeError:
        return 0, "I could not reliably mark that answer. Try again with a clearer answer."

    if not isinstance(parsed, dict):
        return 0, "I could not reliably mark that answer. Try again with a clearer answer."

    explanation = str(parsed.get("explanation", "")).strip() or "No explanation was provided."
    awarded_marks = _coerce_marks(parsed.get("awarded_marks"), max_marks=max_marks)
    return awarded_marks, explanation


def _coerce_marks(value, *, max_marks: int) -> int:
    parsed = 0
    if isinstance(value, bool):
        parsed = int(value)
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = round(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped:
            try:
                parsed = round(float(stripped))
            except ValueError:
                parsed = 0
    return max(0, min(max_marks, parsed))


def _strip_json_fence(raw_response: str) -> str:
    stripped = raw_response.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _validate_selector_overrides(
    *,
    course: Course,
    selector_override_topic: CourseTopic | None,
    selector_override_question: CourseQuestion | None,
) -> None:
    if selector_override_topic is not None and selector_override_topic.course_id != course.id:
        raise ValueError("selector_override_topic must belong to the selected course.")
    if selector_override_question is not None and selector_override_question.course_id != course.id:
        raise ValueError("selector_override_question must belong to the selected course.")
