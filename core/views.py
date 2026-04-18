from django.shortcuts import render
from django.urls import reverse


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
            "course_topics_page_url": reverse("course-topics"),
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
        },
    )
