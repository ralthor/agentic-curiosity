from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache

from chat_api.rate_limits import (
    clear_failed_logins,
    get_login_rate_limit_status,
    get_rate_limit_now,
    register_failed_login,
)


def home(request):
    return render(
        request,
        "core/home.html",
        {
            "chat_api_login_url": reverse("chat-api-login"),
            "chat_api_token_url": reverse("chat-api-token"),
            "chat_api_courses_url": reverse("chat-api-courses"),
            "chat_api_sessions_url": reverse("chat-api-create-session"),
            "chat_api_chat_url": reverse("chat-api-chat"),
            "chat_api_answer_photos_url": reverse("chat-api-answer-photos"),
            "chat_api_session_detail_base_url": reverse("chat-api-session-detail", args=[0]).removesuffix("0/"),
            "course_topics_page_url": reverse("course-topics"),
            "course_questions_page_url": reverse("course-questions"),
            "attempts_page_url": reverse("attempts"),
        },
    )


def course_topics(request):
    return render(
        request,
        "core/course_topics.html",
        {
            "chat_api_token_url": reverse("chat-api-token"),
            "chat_api_courses_url": reverse("chat-api-courses"),
            "home_url": reverse("home"),
            "course_questions_page_url": reverse("course-questions"),
        },
    )


def course_questions(request):
    return render(
        request,
        "core/course_questions.html",
        {
            "chat_api_token_url": reverse("chat-api-token"),
            "chat_api_courses_url": reverse("chat-api-courses"),
            "home_url": reverse("home"),
            "course_topics_page_url": reverse("course-topics"),
            "attempts_page_url": reverse("attempts"),
        },
    )


def attempts(request):
    return render(
        request,
        "core/attempts.html",
        {
            "chat_api_login_url": reverse("chat-api-login"),
            "chat_api_courses_url": reverse("chat-api-courses"),
            "chat_api_attempts_url": reverse("chat-api-attempts"),
            "home_url": reverse("home"),
            "course_topics_page_url": reverse("course-topics"),
            "course_questions_page_url": reverse("course-questions"),
        },
    )


def _build_admin_login_rate_limit_response(request, *, username: str, retry_after_seconds: int) -> TemplateResponse:
    form = AdminAuthenticationForm(request=request, initial={"username": username})
    form.full_clean()
    if not hasattr(form, "cleaned_data"):
        form.cleaned_data = {}
    form.add_error(None, f"Too many login attempts. Try again in {retry_after_seconds} seconds.")

    context = {
        **admin.site.each_context(request),
        "title": "Log in",
        "subtitle": None,
        "app_path": request.get_full_path(),
        "username": request.user.get_username(),
        "form": form,
    }
    if REDIRECT_FIELD_NAME not in request.GET and REDIRECT_FIELD_NAME not in request.POST:
        context[REDIRECT_FIELD_NAME] = reverse("admin:index", current_app=admin.site.name)

    request.current_app = admin.site.name
    response = TemplateResponse(
        request,
        admin.site.login_template or "admin/login.html",
        context,
        status=429,
    )
    response["Retry-After"] = str(retry_after_seconds)
    return response


@never_cache
def admin_login(request):
    if request.method != "POST":
        return admin.site.login(request)

    username = str(request.POST.get("username", "")).strip()
    if not username:
        return admin.site.login(request)

    rate_limit_now = get_rate_limit_now()
    rate_limit_status = get_login_rate_limit_status(request=request, username=username, now=rate_limit_now)
    if rate_limit_status.is_limited:
        return _build_admin_login_rate_limit_response(
            request,
            username=username,
            retry_after_seconds=rate_limit_status.retry_after_seconds,
        )

    response = admin.site.login(request)
    if request.user.is_authenticated and request.user.is_staff and 300 <= response.status_code < 400:
        clear_failed_logins(request=request, username=username)
        return response

    register_failed_login(request=request, username=username, now=rate_limit_now)
    return response
