from django.urls import path

from .views import chat_view, create_session_view, login_view, token_view

urlpatterns = [
    path("login/", login_view, name="chat-api-login"),
    path("token/", token_view, name="chat-api-token"),
    path("sessions/", create_session_view, name="chat-api-create-session"),
    path("chat/", chat_view, name="chat-api-chat"),
]
