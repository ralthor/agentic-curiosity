from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from .models import LoginRateLimit


@dataclass(frozen=True)
class LoginRateLimitStatus:
    is_limited: bool
    retry_after_seconds: int = 0


def get_rate_limit_now():
    return timezone.now()


def _rate_limit_attempts() -> int:
    return max(1, int(getattr(settings, "LOGIN_RATE_LIMIT_ATTEMPTS", 10)))


def _rate_limit_window_seconds() -> int:
    return max(1, int(getattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 20)))


def _normalized_username(username: str) -> str:
    return username.strip().casefold()


def _client_identifier(request) -> str:
    real_ip = str(request.META.get("HTTP_X_REAL_IP", "")).strip()
    if real_ip:
        return real_ip

    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR", "")).strip()
    if forwarded_for:
        forwarded_values = [value.strip() for value in forwarded_for.split(",") if value.strip()]
        if forwarded_values:
            return forwarded_values[0]

    remote_addr = str(request.META.get("REMOTE_ADDR", "")).strip()
    if remote_addr:
        return remote_addr

    return "unknown"


def _to_epoch_seconds(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _prune_failures(failed_attempts: list[object], *, now_seconds: float) -> list[float]:
    cutoff = now_seconds - _rate_limit_window_seconds()
    return [attempted_at for attempted_at in (_to_epoch_seconds(value) for value in failed_attempts) if attempted_at > cutoff]


def _load_recent_failures(*, request, username: str, now_seconds: float) -> list[float]:
    entry = LoginRateLimit.objects.filter(
        username_key=_normalized_username(username),
        client_identifier=_client_identifier(request),
    ).first()
    if entry is None:
        return []

    recent_failures = _prune_failures(entry.failed_attempt_timestamps, now_seconds=now_seconds)
    if recent_failures != entry.failed_attempt_timestamps:
        if recent_failures:
            entry.failed_attempt_timestamps = recent_failures
            entry.save(update_fields=["failed_attempt_timestamps", "updated_at"])
        else:
            entry.delete()
    return recent_failures


def get_login_rate_limit_status(*, request, username: str, now=None) -> LoginRateLimitStatus:
    current_time = now or get_rate_limit_now()
    now_seconds = current_time.timestamp()
    recent_failures = _load_recent_failures(request=request, username=username, now_seconds=now_seconds)
    if len(recent_failures) < _rate_limit_attempts():
        return LoginRateLimitStatus(is_limited=False)

    retry_after_seconds = max(
        1,
        ceil((recent_failures[0] + _rate_limit_window_seconds()) - now_seconds),
    )
    return LoginRateLimitStatus(is_limited=True, retry_after_seconds=retry_after_seconds)


def register_failed_login(*, request, username: str, now=None) -> None:
    current_time = now or get_rate_limit_now()
    now_seconds = current_time.timestamp()

    with transaction.atomic():
        entry, _created = LoginRateLimit.objects.select_for_update().get_or_create(
            username_key=_normalized_username(username),
            client_identifier=_client_identifier(request),
            defaults={"failed_attempt_timestamps": []},
        )
        recent_failures = _prune_failures(entry.failed_attempt_timestamps, now_seconds=now_seconds)
        recent_failures.append(now_seconds)
        entry.failed_attempt_timestamps = recent_failures
        entry.save(update_fields=["failed_attempt_timestamps", "updated_at"])


def clear_failed_logins(*, request, username: str) -> None:
    LoginRateLimit.objects.filter(
        username_key=_normalized_username(username),
        client_identifier=_client_identifier(request),
    ).delete()


def build_login_rate_limit_response(status: LoginRateLimitStatus) -> JsonResponse:
    response = JsonResponse(
        {
            "error": f"Too many login attempts. Try again in {status.retry_after_seconds} seconds.",
            "retry_after_seconds": status.retry_after_seconds,
        },
        status=429,
    )
    response["Retry-After"] = str(status.retry_after_seconds)
    return response
