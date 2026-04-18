from django.urls import path

from .views import attempts, course_topics, home

urlpatterns = [
    path('', home, name='home'),
    path('course-topics/', course_topics, name='course-topics'),
    path('attempts/', attempts, name='attempts'),
]
