from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from ai_chat.models import LearnerQuestionState

from .models import Course, CourseQuestion, CourseTopic


@dataclass(frozen=True)
class QuestionSelection:
    question: CourseQuestion
    source: str


def select_next_question(
    *,
    user_id: str | int,
    course: Course,
    session,
    topic_override: CourseTopic | None = None,
    question_override: CourseQuestion | None = None,
    strategy_override: str | None = None,
    exclude_question_id: int | None = None,
) -> QuestionSelection | None:
    resolved_user_id = str(user_id)
    resolved_question_override = question_override or session.selector_override_question
    if resolved_question_override is not None:
        if resolved_question_override.course_id != course.id:
            raise ValueError("selector question override must belong to the session course.")
        if exclude_question_id is None or resolved_question_override.id != exclude_question_id:
            return QuestionSelection(question=resolved_question_override, source="explicit_question")

    resolved_topic_override = topic_override or session.selector_override_topic
    resolved_strategy = (strategy_override or session.selector_strategy_override or "").strip().lower()

    questions = list(
        course.questions.select_related("topic", "question_type").order_by("topic_id", "id")
    )
    if exclude_question_id is not None:
        questions = [question for question in questions if question.id != exclude_question_id]
    if resolved_topic_override is not None:
        if resolved_topic_override.course_id != course.id:
            raise ValueError("selector topic override must belong to the session course.")
        questions = [question for question in questions if question.topic_id == resolved_topic_override.id]
        if not questions:
            return None

    if resolved_strategy == "same_topic":
        recent_topic_id = _recent_topic_id(session)
        if recent_topic_id is not None:
            same_topic_questions = [question for question in questions if question.topic_id == recent_topic_id]
            if same_topic_questions:
                questions = same_topic_questions

    if not questions:
        return None

    question_ids = [question.id for question in questions]
    states = {
        state.question_id: state
        for state in LearnerQuestionState.objects.filter(
            user_id=resolved_user_id,
            course=course,
            question_id__in=question_ids,
        )
    }
    topic_summary = _build_topic_summary(questions=questions, states=states)
    now = timezone.now()
    recent_topic_id = _recent_topic_id(session)

    unseen_questions = [question for question in questions if question.id not in states or states[question.id].times_seen == 0]
    due_questions = [
        question
        for question in questions
        if question.id in states and states[question.id].due_at <= now
    ]
    if unseen_questions:
        pool = unseen_questions
        source = "default_unseen"
    elif due_questions:
        pool = due_questions
        source = "default_due"
    else:
        pool = questions
        source = "default_fallback"

    distinct_topic_count = len({question.topic_id for question in pool})

    def priority(question: CourseQuestion) -> tuple:
        state = states.get(question.id)
        summary = topic_summary[question.topic_id]
        seen_count = state.times_seen if state is not None else 0
        due_at = state.due_at if state is not None else now
        recent_topic_penalty = 0
        if distinct_topic_count > 1 and recent_topic_id is not None and question.topic_id == recent_topic_id:
            recent_topic_penalty = 1
        return (
            recent_topic_penalty,
            summary["coverage_pct"],
            summary["mastery_pct"],
            due_at,
            seen_count,
            question.id,
        )

    return QuestionSelection(question=min(pool, key=priority), source=source)


def _recent_topic_id(session) -> int | None:
    return (
        session.presentations.order_by("-opened_at", "-id")
        .values_list("question__topic_id", flat=True)
        .first()
    )


def _build_topic_summary(*, questions: list[CourseQuestion], states: dict[int, LearnerQuestionState]) -> dict[int, dict[str, int]]:
    by_topic: dict[int, dict[str, int]] = {}
    for question in questions:
        state = states.get(question.id)
        summary = by_topic.setdefault(
            question.topic_id,
            {"question_count": 0, "seen_count": 0, "mastery_sum": 0},
        )
        summary["question_count"] += 1
        if state is not None and state.times_seen > 0:
            summary["seen_count"] += 1
            summary["mastery_sum"] += state.latest_leitner_score

    for summary in by_topic.values():
        question_count = max(summary["question_count"], 1)
        summary["coverage_pct"] = round((summary["seen_count"] / question_count) * 100)
        summary["mastery_pct"] = round((summary["mastery_sum"] / (question_count * 4)) * 100)
    return by_topic
