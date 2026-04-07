from django.shortcuts import render
from django.urls import reverse


def home(request):
    return render(
        request,
        "core/home.html",
        {
            "chat_api_login_url": reverse("chat-api-login"),
            "chat_api_token_url": reverse("chat-api-token"),
            "chat_api_course_topics_url": reverse("chat-api-course-topics"),
            "chat_api_sessions_url": reverse("chat-api-create-session"),
            "chat_api_chat_url": reverse("chat-api-chat"),
            "course_topics_page_url": reverse("course-topics"),
        },
    )


def course_topics(request):
    return render(
        request,
        "core/course_topics.html",
        {
            "chat_api_token_url": reverse("chat-api-token"),
            "chat_api_course_topics_url": reverse("chat-api-course-topics"),
            "home_url": reverse("home"),
        },
    )
