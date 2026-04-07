from django.contrib import admin

from .models import ApiToken, CourseTopic


@admin.register(CourseTopic)
class CourseTopicAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name", "id")


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "key")
    ordering = ("user_id",)
