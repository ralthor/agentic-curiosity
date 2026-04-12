from __future__ import annotations

import json

from django.contrib.auth import authenticate, login as django_login
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ai_chat.models import ChatSession

from .auth import get_user_from_authorization_header
from .models import ApiToken, Course, CourseQuestion, CourseTopic, QuestionType
from .progress import build_course_progress, serialize_active_question
from .services import create_session, get_session, interact_with_session


def _json_error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def _load_json_body(request) -> dict:
    if not request.body:
        return {}

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    return payload


def _require_token_user(request):
    user = get_user_from_authorization_header(request)
    if user is None:
        return None, _json_error(
            "Authentication credentials were not provided or are invalid.",
            status=401,
        )

    return user, None


def _parse_positive_int(raw_value) -> int | None:
    if isinstance(raw_value, int) and raw_value > 0:
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        parsed = int(raw_value.strip())
        if parsed > 0:
            return parsed
    return None


def _require_non_blank_string(payload: dict, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank.")
    return value.strip()


def _optional_string(payload: dict, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _require_object_list(payload: dict, field_name: str) -> list[dict]:
    value = payload.get(field_name, [])
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list.")
    normalized: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"Each item in {field_name} must be an object.")
        normalized.append(item)
    return normalized


def _serialize_course(course: Course) -> dict[str, object]:
    topics = list(course.topics.order_by("name", "id"))
    question_types = list(course.question_types.order_by("name", "id"))
    topic_question_counts = {
        row["topic_id"]: row["count"]
        for row in course.questions.values("topic_id").order_by().annotate(count=Count("id"))
    }
    return {
        "id": course.pk,
        "name": course.name,
        "topic_count": len(topics),
        "question_type_count": len(question_types),
        "question_count": course.questions.count(),
        "topics": [
            {
                "id": topic.pk,
                "name": topic.name,
                "import_key": topic.import_key,
                "question_count": topic_question_counts.get(topic.pk, 0),
            }
            for topic in topics
        ],
        "question_types": [
            {
                "id": question_type.pk,
                "name": question_type.name,
                "import_key": question_type.import_key,
            }
            for question_type in question_types
        ],
        "created_at": course.created_at.isoformat(),
        "updated_at": course.updated_at.isoformat(),
    }


def _serialize_session(session: ChatSession) -> dict[str, object]:
    course_progress = build_course_progress(course=session.course, user_id=session.user_id)
    active_question = serialize_active_question(session.active_presentation)
    return {
        "session_id": session.pk,
        "course": {
            "id": session.course.pk,
            "name": session.course.name,
        },
        "active_question": active_question,
        "active_topic": active_question["topic"] if active_question is not None else None,
        "selection_source": active_question["selection_source"] if active_question is not None else None,
        "course_progress": {
            "coverage_pct": course_progress["coverage_pct"],
            "mastery_pct": course_progress["mastery_pct"],
            "questions_seen": course_progress["questions_seen"],
            "question_count": course_progress["question_count"],
        },
        "topic_progress": course_progress["topic_progress"],
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def _resolve_course_topic_for_payload(*, course: Course, item: dict) -> CourseTopic:
    topic_id = _parse_positive_int(item.get("topic_id"))
    topic_import_key = _optional_string(item, "topic_import_key")
    topic_name = _optional_string(item, "topic_name")

    queryset = course.topics.all()
    if topic_id is not None:
        topic = queryset.filter(pk=topic_id).first()
        if topic is not None:
            return topic
    if topic_import_key:
        topic = queryset.filter(import_key=topic_import_key).first()
        if topic is not None:
            return topic
    if topic_name:
        topic = queryset.filter(name=topic_name).first()
        if topic is not None:
            return topic
    raise ValueError("Each question must reference a valid topic_id, topic_import_key, or topic_name.")


def _resolve_question_type_for_payload(*, course: Course, item: dict) -> QuestionType:
    question_type_id = _parse_positive_int(item.get("question_type_id"))
    question_type_import_key = _optional_string(item, "question_type_import_key")
    question_type_name = _optional_string(item, "question_type_name")

    queryset = course.question_types.all()
    if question_type_id is not None:
        question_type = queryset.filter(pk=question_type_id).first()
        if question_type is not None:
            return question_type
    if question_type_import_key:
        question_type = queryset.filter(import_key=question_type_import_key).first()
        if question_type is not None:
            return question_type
    if question_type_name:
        question_type = queryset.filter(name=question_type_name).first()
        if question_type is not None:
            return question_type
    raise ValueError("Each question must reference a valid question_type_id, question_type_import_key, or question_type_name.")


def _create_course_from_payload(payload: dict) -> Course:
    topics_payload = _require_object_list(payload, "topics")
    question_types_payload = _require_object_list(payload, "question_types")
    questions_payload = _require_object_list(payload, "questions")

    with transaction.atomic():
        course = Course.objects.create(name=_require_non_blank_string(payload, "name"))

        for topic_payload in topics_payload:
            CourseTopic.objects.create(
                course=course,
                name=_require_non_blank_string(topic_payload, "name"),
                import_key=_optional_string(topic_payload, "import_key"),
            )

        for question_type_payload in question_types_payload:
            QuestionType.objects.create(
                course=course,
                name=_require_non_blank_string(question_type_payload, "name"),
                hint_prompt=_require_non_blank_string(question_type_payload, "hint_prompt"),
                mark_prompt=_require_non_blank_string(question_type_payload, "mark_prompt"),
                import_key=_optional_string(question_type_payload, "import_key"),
            )

        _create_questions_for_course(course=course, questions_payload=questions_payload)

    return course


def _create_questions_for_course(*, course: Course, questions_payload: list[dict]) -> int:
    created_count = 0
    for question_payload in questions_payload:
        max_marks = _parse_positive_int(question_payload.get("max_marks"))
        if max_marks is None:
            raise ValueError("Each question must include a positive integer max_marks.")
        question = CourseQuestion(
            course=course,
            topic=_resolve_course_topic_for_payload(course=course, item=question_payload),
            question_type=_resolve_question_type_for_payload(course=course, item=question_payload),
            question_text=_require_non_blank_string(question_payload, "question_text"),
            max_marks=max_marks,
            sample_answer=_optional_string(question_payload, "sample_answer"),
            example_answer=_optional_string(question_payload, "example_answer"),
            marking_notes=_optional_string(question_payload, "marking_notes"),
            import_key=_optional_string(question_payload, "import_key"),
        )
        question.full_clean()
        question.save()
        created_count += 1
    return created_count


def _resolve_selector_override_topic(course: Course, payload: dict) -> CourseTopic | None:
    topic_id = _parse_positive_int(payload.get("selector_override_topic_id"))
    if topic_id is None:
        return None
    return course.topics.filter(pk=topic_id).first()


def _resolve_selector_override_question(course: Course, payload: dict) -> CourseQuestion | None:
    question_id = _parse_positive_int(payload.get("selector_override_question_id"))
    if question_id is None:
        return None
    return course.questions.filter(pk=question_id).first()


@csrf_exempt
@require_POST
def login_view(request):
    try:
        payload = _load_json_body(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    username = str(payload.get("username", "")).strip()
    password = payload.get("password")
    if not username or not isinstance(password, str) or not password:
        return _json_error("username and password are required.", status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return _json_error("Invalid username or password.", status=401)

    django_login(request, user)
    token = ApiToken.issue_for_user(user)
    return JsonResponse(
        {
            "token": token.key,
            "user_id": user.pk,
            "username": user.get_username(),
        }
    )


@csrf_exempt
@require_POST
def token_view(request):
    if not request.user.is_authenticated:
        return _json_error("Login required.", status=401)

    token = ApiToken.issue_for_user(request.user)
    return JsonResponse(
        {
            "token": token.key,
            "user_id": request.user.pk,
            "username": request.user.get_username(),
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def courses_view(request):
    user, error_response = _require_token_user(request)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        courses = Course.objects.order_by("name", "id")
        return JsonResponse({"courses": [_serialize_course(course) for course in courses]})

    try:
        payload = _load_json_body(request)
        course = _create_course_from_payload(payload)
    except (IntegrityError, ValidationError, ValueError) as exc:
        return _json_error(str(exc), status=400)

    return JsonResponse({"course": _serialize_course(course)}, status=201)


@csrf_exempt
@require_POST
def import_course_questions_view(request, course_id: int):
    _user, error_response = _require_token_user(request)
    if error_response is not None:
        return error_response

    course = Course.objects.filter(pk=course_id).first()
    if course is None:
        return _json_error("Course not found.", status=404)

    try:
        payload = _load_json_body(request)
        questions_payload = _require_object_list(payload, "questions")
        if not questions_payload:
            raise ValueError("questions must contain at least one item.")
        with transaction.atomic():
            created_count = _create_questions_for_course(course=course, questions_payload=questions_payload)
    except (IntegrityError, ValidationError, ValueError) as exc:
        return _json_error(str(exc), status=400)

    return JsonResponse(
        {
            "course": _serialize_course(course),
            "imported_question_count": created_count,
        },
        status=201,
    )


@csrf_exempt
@require_POST
def create_session_view(request):
    user, error_response = _require_token_user(request)
    if error_response is not None:
        return error_response

    try:
        payload = _load_json_body(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    course_id = _parse_positive_int(payload.get("course_id"))
    if course_id is None:
        return _json_error("course_id must be a positive integer.", status=400)

    course = Course.objects.filter(pk=course_id).first()
    if course is None:
        return _json_error("Course not found.", status=404)

    selector_override_topic = _resolve_selector_override_topic(course, payload)
    if payload.get("selector_override_topic_id") and selector_override_topic is None:
        return _json_error("selector_override_topic_id must reference a topic in the selected course.", status=400)

    selector_override_question = _resolve_selector_override_question(course, payload)
    if payload.get("selector_override_question_id") and selector_override_question is None:
        return _json_error("selector_override_question_id must reference a question in the selected course.", status=400)

    try:
        session = create_session(
            user=user,
            course=course,
            selector_override_topic=selector_override_topic,
            selector_override_question=selector_override_question,
            selector_strategy_override=_optional_string(payload, "selector_strategy_override"),
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    return JsonResponse(_serialize_session(session), status=201)


@csrf_exempt
@require_GET
def session_detail_view(request, session_id: int):
    user, error_response = _require_token_user(request)
    if error_response is not None:
        return error_response

    try:
        session = get_session(user=user, session_id=session_id)
    except ChatSession.DoesNotExist:
        return _json_error("Session not found.", status=404)

    return JsonResponse(_serialize_session(session))


@csrf_exempt
@require_POST
def chat_view(request):
    user, error_response = _require_token_user(request)
    if error_response is not None:
        return error_response

    try:
        payload = _load_json_body(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    session_id = _parse_positive_int(payload.get("session_id"))
    if session_id is None:
        return _json_error("session_id must be a positive integer.", status=400)

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return _json_error("text must not be blank.", status=400)

    try:
        session, interaction_result = interact_with_session(user=user, session_id=session_id, text=text)
    except ChatSession.DoesNotExist:
        return _json_error("Session not found.", status=404)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    payload = _serialize_session(session)
    payload.update(
        {
            "interaction_type": interaction_result.interaction_type,
            "message": interaction_result.message,
            "awarded_marks": interaction_result.awarded_marks,
            "derived_leitner_score": interaction_result.derived_leitner_score,
            "completed_presentation": interaction_result.completed_presentation,
        }
    )
    return JsonResponse(payload)
