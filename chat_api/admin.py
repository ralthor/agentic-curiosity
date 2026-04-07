from django.contrib import admin

from .course_state import normalize_expectations
from .models import ApiToken, CourseTopic


@admin.register(CourseTopic)
class CourseTopicAdmin(admin.ModelAdmin):
    list_display = ("name", "expectation_count", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name", "id")

    @admin.display(description="Expectations")
    def expectation_count(self, obj: CourseTopic) -> int:
        return len(normalize_expectations(obj.expectations))


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "key")
    ordering = ("user_id",)
