from __future__ import annotations

import json

from django.contrib.auth import authenticate, login as django_login
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ai_chat.models import ChatSession

from .auth import get_user_from_authorization_header
from .models import ApiToken, CourseTopic
from .services import build_chat, create_session, get_session


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


def _parse_session_id(raw_value) -> int | None:
    if isinstance(raw_value, int) and raw_value > 0:
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        parsed = int(raw_value.strip())
        if parsed > 0:
            return parsed
    return None


def _serialize_course_topic(course_topic: CourseTopic) -> dict:
    return {
        "id": course_topic.pk,
        "name": course_topic.name,
        "teacher_prompt": course_topic.teacher_prompt,
        "judge_prompt": course_topic.judge_prompt,
        "categorizer_prompt": course_topic.categorizer_prompt,
        "answerer_prompt": course_topic.answerer_prompt,
        "planner_prompt": course_topic.planner_prompt,
        "briefer_prompt": course_topic.briefer_prompt,
        "created_at": course_topic.created_at.isoformat(),
        "updated_at": course_topic.updated_at.isoformat(),
    }


def _serialize_session(session) -> dict:
    course_topic = session.course_topic
    serialized_topic = None
    if course_topic is not None:
        serialized_topic = {
            "id": course_topic.pk,
            "name": course_topic.name,
        }

    return {
        "session_id": session.pk,
        "course_topic": serialized_topic,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def _require_non_blank_string(payload: dict, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank.")
    return value.strip()


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
@require_POST
def create_session_view(request):
    user, error_response = _require_token_user(request)
    if error_response is not None:
        return error_response

    try:
        payload = _load_json_body(request)
    except ValueError as exc:
        return _json_error(str(exc), status=400)

    course_topic_id = _parse_session_id(payload.get("course_topic_id"))
    if course_topic_id is None:
        return _json_error("course_topic_id must be a positive integer.", status=400)

    course_topic = CourseTopic.objects.filter(pk=course_topic_id).first()
    if course_topic is None:
        return _json_error("Course topic not found.", status=404)

    session = create_session(user=user, course_topic=course_topic)
    return JsonResponse(_serialize_session(session), status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def course_topics_view(request):
    user, error_response = _require_token_user(request)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        topics = CourseTopic.objects.order_by("name", "id")
        return JsonResponse({"topics": [_serialize_course_topic(topic) for topic in topics]})

    try:
        payload = _load_json_body(request)
        topic = CourseTopic.objects.create(
            name=_require_non_blank_string(payload, "name"),
            teacher_prompt=_require_non_blank_string(payload, "teacher_prompt"),
            judge_prompt=_require_non_blank_string(payload, "judge_prompt"),
            categorizer_prompt=_require_non_blank_string(payload, "categorizer_prompt"),
            answerer_prompt=_require_non_blank_string(payload, "answerer_prompt"),
            planner_prompt=_require_non_blank_string(payload, "planner_prompt"),
            briefer_prompt=_require_non_blank_string(payload, "briefer_prompt"),
        )
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except IntegrityError:
        return _json_error("A course topic with that name already exists.", status=400)

    return JsonResponse({"topic": _serialize_course_topic(topic)}, status=201)


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

    session_id = _parse_session_id(payload.get("session_id"))
    if session_id is None:
        return _json_error("session_id must be a positive integer.", status=400)

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return _json_error("text must not be blank.", status=400)

    try:
        session = get_session(user=user, session_id=session_id)
    except ChatSession.DoesNotExist:
        return _json_error("Session not found.", status=404)

    if session.course_topic is None:
        return _json_error("Session does not have a course topic.", status=409)

    try:
        chat = build_chat(user=user, session_id=session_id, course_topic=session.course_topic)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    response = chat.reply(text)
    return JsonResponse(
        {
            "session_id": session_id,
            "response": response,
        }
    )
