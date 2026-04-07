from django.urls import path

from .views import (
    chat_view,
    course_topics_view,
    create_session_view,
    login_view,
    session_detail_view,
    token_view,
)

urlpatterns = [
    path("login/", login_view, name="chat-api-login"),
    path("token/", token_view, name="chat-api-token"),
    path("course-topics/", course_topics_view, name="chat-api-course-topics"),
    path("sessions/", create_session_view, name="chat-api-create-session"),
    path("sessions/<int:session_id>/", session_detail_view, name="chat-api-session-detail"),
    path("chat/", chat_view, name="chat-api-chat"),
]
