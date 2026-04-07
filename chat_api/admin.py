from django.contrib import admin

from .models import ApiToken


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "key")
    ordering = ("user_id",)
