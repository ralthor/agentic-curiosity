from django.urls import path

from .views import attempts, course_questions, course_topics, home

urlpatterns = [
    path('', home, name='home'),
    path('course-topics/', course_topics, name='course-topics'),
    path('course-questions/', course_questions, name='course-questions'),
    path('attempts/', attempts, name='attempts'),
]
