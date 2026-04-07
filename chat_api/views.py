from __future__ import annotations

import json

from django.contrib.auth import authenticate, login as django_login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ai_chat.models import ChatSession

from .auth import get_user_from_authorization_header
from .models import ApiToken
from .services import build_chat, create_session


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
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        return int(raw_value.strip())
    return None


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

    session = create_session(user=user)
    return JsonResponse({"session_id": session.pk}, status=201)


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

    if not ChatSession.objects.filter(pk=session_id, user_id=str(user.pk)).exists():
        return _json_error("Session not found.", status=404)

    chat = build_chat(user=user, session_id=session_id)
    response = chat.reply(text)
    return JsonResponse(
        {
            "session_id": session_id,
            "response": response,
        }
    )
