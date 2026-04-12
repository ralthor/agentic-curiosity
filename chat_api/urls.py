from django.urls import path

from .views import (
    chat_view,
    courses_view,
    create_session_view,
    import_course_questions_view,
    login_view,
    session_detail_view,
    token_view,
)

urlpatterns = [
    path("login/", login_view, name="chat-api-login"),
    path("token/", token_view, name="chat-api-token"),
    path("courses/", courses_view, name="chat-api-courses"),
    path("courses/<int:course_id>/questions/import/", import_course_questions_view, name="chat-api-import-course-questions"),
    path("sessions/", create_session_view, name="chat-api-create-session"),
    path("sessions/<int:session_id>/", session_detail_view, name="chat-api-session-detail"),
    path("chat/", chat_view, name="chat-api-chat"),
]
