from django.contrib import admin

from .models import ApiToken, Course, CourseQuestion, CourseTopic, QuestionType


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "topic_count", "question_type_count", "question_count", "created_at", "updated_at")
    search_fields = ("name",)
    ordering = ("name", "id")

    @admin.display(description="Topics")
    def topic_count(self, obj: Course) -> int:
        return obj.topics.count()

    @admin.display(description="Question Types")
    def question_type_count(self, obj: Course) -> int:
        return obj.question_types.count()

    @admin.display(description="Questions")
    def question_count(self, obj: Course) -> int:
        return obj.questions.count()


@admin.register(CourseTopic)
class CourseTopicAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "question_count", "created_at", "updated_at")
    list_select_related = ("course",)
    search_fields = ("name", "course__name", "import_key")
    ordering = ("course__name", "name", "id")

    @admin.display(description="Questions")
    def question_count(self, obj: CourseTopic) -> int:
        return obj.questions.count()


@admin.register(QuestionType)
class QuestionTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "question_count", "created_at", "updated_at")
    list_select_related = ("course",)
    search_fields = ("name", "course__name", "import_key")
    ordering = ("course__name", "name", "id")

    @admin.display(description="Questions")
    def question_count(self, obj: QuestionType) -> int:
        return obj.questions.count()


@admin.register(CourseQuestion)
class CourseQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "topic", "question_type", "max_marks", "created_at")
    list_select_related = ("course", "topic", "question_type")
    search_fields = ("question_text", "sample_answer", "example_answer", "marking_notes", "import_key")
    ordering = ("course__name", "topic__name", "id")


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "key")
    ordering = ("user_id",)
