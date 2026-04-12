from __future__ import annotations

from datetime import timedelta

from ai_chat.models import LearnerQuestionState, QuestionPresentation

from .models import Course


def derive_leitner_score(*, awarded_marks: int, max_marks: int) -> int:
    if max_marks <= 0:
        return 0

    ratio = awarded_marks / max_marks
    if ratio <= 0:
        return 0
    if ratio < 0.5:
        return 1
    if ratio < 0.75:
        return 2
    if ratio < 1:
        return 3
    return 4


def schedule_due_at(*, from_time, leitner_score: int):
    offsets = {
        0: timedelta(seconds=0),
        1: timedelta(days=1),
        2: timedelta(days=3),
        3: timedelta(days=7),
        4: timedelta(days=21),
    }
    return from_time + offsets.get(max(0, min(4, leitner_score)), timedelta(seconds=0))


def build_course_progress(*, course: Course, user_id: str | int) -> dict[str, object]:
    questions = list(course.questions.select_related("topic").order_by("topic_id", "id"))
    states = {
        state.question_id: state
        for state in LearnerQuestionState.objects.filter(user_id=str(user_id), course=course).select_related("question__topic")
    }
    topic_rows: dict[int, dict[str, object]] = {}
    for topic in course.topics.order_by("name", "id"):
        topic_rows[topic.id] = {
            "id": topic.id,
            "name": topic.name,
            "question_count": 0,
            "questions_seen": 0,
            "coverage_pct": 0,
            "mastery_pct": 0,
            "mastery_points": 0,
        }

    total_seen = 0
    mastery_sum = 0
    for question in questions:
        topic_row = topic_rows[question.topic_id]
        topic_row["question_count"] += 1
        state = states.get(question.id)
        if state is None:
            continue
        mastery_sum += state.latest_leitner_score
        topic_row["mastery_points"] += state.latest_leitner_score
        if state.times_seen > 0:
            total_seen += 1
            topic_row["questions_seen"] += 1

    topic_progress: list[dict[str, object]] = []
    for topic_id in sorted(topic_rows, key=lambda candidate: (topic_rows[candidate]["name"], candidate)):
        row = topic_rows[topic_id]
        question_count = row["question_count"] or 0
        if question_count:
            row["coverage_pct"] = round((row["questions_seen"] / question_count) * 100)
            row["mastery_pct"] = round((row["mastery_points"] / (question_count * 4)) * 100)
        topic_progress.append(row)

    question_count = len(questions)
    return {
        "coverage_pct": round((total_seen / question_count) * 100) if question_count else 0,
        "mastery_pct": round((mastery_sum / (question_count * 4)) * 100) if question_count else 0,
        "questions_seen": total_seen,
        "question_count": question_count,
        "topic_progress": topic_progress,
    }


def serialize_active_question(presentation: QuestionPresentation | None) -> dict[str, object] | None:
    if presentation is None:
        return None

    question = presentation.question
    topic = question.topic
    question_type = question.question_type
    return {
        "presentation_id": presentation.pk,
        "question_id": question.pk,
        "question_text": question.question_text,
        "max_marks": question.max_marks,
        "status": presentation.status,
        "selection_source": presentation.selection_source,
        "attempt_count": presentation.attempts.count(),
        "topic": {
            "id": topic.pk,
            "name": topic.name,
        },
        "question_type": {
            "id": question_type.pk,
            "name": question_type.name,
        },
        "opened_at": presentation.opened_at.isoformat(),
        "closed_at": presentation.closed_at.isoformat() if presentation.closed_at is not None else None,
    }
