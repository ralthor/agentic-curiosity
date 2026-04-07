from django.shortcuts import render
from django.urls import reverse


def home(request):
    return render(
        request,
        "core/home.html",
        {
            "chat_api_login_url": reverse("chat-api-login"),
            "chat_api_token_url": reverse("chat-api-token"),
            "chat_api_sessions_url": reverse("chat-api-create-session"),
            "chat_api_chat_url": reverse("chat-api-chat"),
        },
    )
